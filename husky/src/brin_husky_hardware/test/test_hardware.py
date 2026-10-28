from collections import deque
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from geometry_msgs.msg import TransformStamped
from launch import LaunchContext
from launch.actions import DeclareLaunchArgument, EmitEvent, OpaqueFunction
from launch_ros.actions import Node
from nav_msgs.msg import OccupancyGrid, Odometry
from sensor_msgs.msg import Imu, LaserScan
from tf2_msgs.msg import TFMessage
import pytest
import yaml

from brin_husky_hardware.adapter import HardwareCommand
from brin_husky_hardware.bridge import (
    PhysicalTfBridge, prefixed_frame, rewrite_transforms, valid_sources)
from brin_husky_hardware.preflight import (
    NativeControllerProbe, distance_to_graph, existing_rmf_processes,
    expected_map, map_geometry_errors,
    profile_match_errors, rmf_core_errors, unexpected_rmf_processes)
from brin_husky_hardware.send_task import request_payload


ROOT = Path(__file__).resolve().parents[2]


def test_tf_is_prefixed_once_and_map_remains_shared():
    message = TFMessage()
    for parent, child in [('map', 'odom'), ('odom', 'base_link'),
                          ('base_link', 'laser_frame')]:
        transform = TransformStamped()
        transform.header.frame_id = parent
        transform.child_frame_id = child
        message.transforms.append(transform)
    converted = rewrite_transforms(message, 'husky_0')
    assert [(t.header.frame_id, t.child_frame_id) for t in converted.transforms] == [
        ('map', 'husky_0/odom'),
        ('husky_0/odom', 'husky_0/base_link'),
        ('husky_0/base_link', 'husky_0/laser_frame')]
    assert prefixed_frame('husky_0/base_link', 'husky_0') == 'husky_0/base_link'


def test_tf_bridge_rejects_output_feedback():
    config = {'tf_topics': ['/a200_1060/tf'],
              'tf_static_topics': ['/a200_1060/tf_static']}
    assert len(valid_sources(config)) == 2
    config['tf_topics'] = ['/tf']
    try:
        valid_sources(config)
        assert False, 'A bridge feedback loop must be rejected'
    except ValueError:
        pass


def test_tf_bridge_detects_duplicate_frame_authority():
    statuses = []
    bridge = SimpleNamespace(
        source_by_child={}, conflict=False,
        status_pub=SimpleNamespace(publish=lambda message: statuses.append(message.data)),
        get_logger=lambda: SimpleNamespace(error=lambda _: None))
    message = TFMessage()
    transform = TransformStamped()
    transform.header.frame_id = 'map'
    transform.child_frame_id = 'husky_0/odom'
    message.transforms.append(transform)
    assert len(PhysicalTfBridge.accepted_transforms(
        bridge, message, '/a200_1060/nav/tf').transforms) == 1
    assert not PhysicalTfBridge.accepted_transforms(
        bridge, message, '/a200_1060/tf').transforms
    assert bridge.conflict and statuses == [True]


@pytest.mark.parametrize('children', [
    ('laser_frame', 'imu_0_link'), ('imu_0_link', 'laser_frame')])
def test_static_tf_burst_preserves_both_publishers(monkeypatch, children):
    """Model queued KEEP_LAST samples arriving before the executor spins."""
    import brin_husky_hardware.bridge as bridge_module

    publishers, subscriptions = {}, {}

    def publisher(self, message_type, topic, qos):
        result = SimpleNamespace(samples=[], qos=qos)
        result.publish = result.samples.append
        publishers[topic] = result
        return result

    def subscription(self, message_type, topic, callback, qos):
        result = SimpleNamespace(callback=callback, queue=deque(maxlen=qos.depth))
        subscriptions[topic] = result
        return result

    config = ROOT / 'brin_husky_distributed/config/husky_0.yaml'
    monkeypatch.setattr(bridge_module.Node, '__init__', lambda self, *a, **kw: None)
    monkeypatch.setattr(bridge_module.Node, 'declare_parameter', lambda *a: None)
    monkeypatch.setattr(bridge_module.Node, 'get_parameter',
                        lambda *a: SimpleNamespace(value=str(config)))
    monkeypatch.setattr(bridge_module.Node, 'create_publisher', publisher)
    monkeypatch.setattr(bridge_module.Node, 'create_subscription', subscription)
    monkeypatch.setattr(bridge_module.Node, 'get_logger',
                        lambda self: SimpleNamespace(info=lambda text: None))
    bridge = PhysicalTfBridge()
    incoming = subscriptions['/a200_1060/tf_static']
    for child in children:
        transform = TransformStamped()
        transform.header.frame_id = 'base_link'
        transform.child_frame_id = child
        transform.transform.rotation.w = 1.0
        incoming.queue.append(TFMessage(transforms=[transform]))
    while incoming.queue:
        incoming.callback(incoming.queue.popleft())
    retained = publishers['/tf_static']
    assert retained.qos.depth == 1
    assert {tf.child_frame_id for tf in retained.samples[-1].transforms} == {
        'husky_0/laser_frame', 'husky_0/imu_0_link'}
    assert not bridge.conflict

def test_sensor_headers_are_prefixed_without_touching_physical_messages():
    outputs = []
    publisher = SimpleNamespace(publish=lambda message: outputs.append(message))
    bridge = SimpleNamespace(robot_name='husky_0', map_frame='map',
                             scan_pub=publisher, odom_pub=publisher,
                             imu_pub=publisher)
    scan = LaserScan()
    scan.header.frame_id = 'laser_frame'
    PhysicalTfBridge.on_scan(bridge, scan)
    odom = Odometry()
    odom.header.frame_id = 'odom'
    odom.child_frame_id = 'base_link'
    PhysicalTfBridge.on_odom(bridge, odom)
    imu = Imu()
    imu.header.frame_id = 'imu_link'
    PhysicalTfBridge.on_imu(bridge, imu)
    assert [message.header.frame_id for message in outputs] == [
        'husky_0/laser_frame', 'husky_0/odom', 'husky_0/imu_link']
    assert outputs[1].child_frame_id == 'husky_0/base_link'
    assert scan.header.frame_id == 'laser_frame'
    assert odom.child_frame_id == 'base_link'


@pytest.mark.parametrize('outcome', ['sigint', 'sigterm', 'runtime_error'])
def test_bridge_stops_executor_before_context_and_reports_runtime_errors(monkeypatch, outcome):
    import brin_husky_hardware.bridge as bridge_module

    events, handlers = [], {}
    original_handler = object()

    def install_handler(sig, handler):
        previous = handlers.get(sig, original_handler)
        handlers[sig] = handler
        return previous

    def initialize(**kwargs):
        assert kwargs['signal_handler_options'] == bridge_module.SignalHandlerOptions.NO

    def spin_once(node, timeout_sec):
        assert timeout_sec <= 0.1
        events.append('spin')
        if outcome == 'runtime_error':
            raise RuntimeError('subscription error')
        sig = (bridge_module.signal.SIGINT if outcome == 'sigint'
               else bridge_module.signal.SIGTERM)
        handlers[sig](sig, None)
        assert events == ['spin']  # Signal handlers must not invalidate ROS entities.

    monkeypatch.setattr(bridge_module.signal, 'signal', install_handler)
    monkeypatch.setattr(bridge_module, 'PhysicalTfBridge',
                        lambda: SimpleNamespace(destroy_node=lambda: events.append('destroy')))
    monkeypatch.setattr(bridge_module.rclpy, 'init', initialize)
    monkeypatch.setattr(bridge_module.rclpy, 'spin_once', spin_once)
    monkeypatch.setattr(bridge_module.rclpy, 'shutdown', lambda: events.append('shutdown'))
    monkeypatch.setattr(bridge_module.rclpy, 'ok', lambda: True)
    if outcome == 'runtime_error':
        with pytest.raises(RuntimeError, match='subscription error'):
            bridge_module.main()
    else:
        bridge_module.main()
    assert events == ['spin', 'destroy', 'shutdown']
    assert all(handler is original_handler for handler in handlers.values())


def test_map_geometry_and_graph_gate():
    maps = ROOT / 'brin_rmf_maps/maps'
    expected = expected_map(maps / 'brin_0.yaml')
    message = OccupancyGrid()
    message.header.frame_id = 'map'
    message.info.width = expected['width']
    message.info.height = expected['height']
    message.info.resolution = expected['resolution']
    message.info.origin.position.x = expected['origin'][0]
    message.info.origin.position.y = expected['origin'][1]
    message.info.origin.orientation.w = 1.0
    assert map_geometry_errors(message, expected) == []
    message.info.origin.position.x += 0.25
    assert 'origin' in map_geometry_errors(message, expected)[0]
    graph = yaml.safe_load((ROOT / 'brin_rmf_maps/nav_graphs/simulation.yaml').read_text())
    vertex = graph['levels']['L1']['vertices'][0]
    assert distance_to_graph(graph, 'L1', vertex[0], vertex[1]) < 1e-6
    assert distance_to_graph(graph, 'L1', -100, -100) > 1.0


def test_physical_failure_never_starts_autonomous_backup():
    reasons = []
    HardwareCommand._start_escape(SimpleNamespace(
        _recovery_failed=lambda reason: reasons.append(reason)))
    assert reasons and 'automatic BackUp is disabled' in reasons[0]


def test_hardware_task_request_uses_wall_clock_and_preserves_cancel():
    payload = request_payload(['ws_p0'], 'husky_0', None, 1_792_400_000_000_000_000)
    assert payload['request']['unix_millis_earliest_start_time'] == 1_792_400_000_000
    assert payload['robot'] == 'husky_0'
    assert request_payload(None, None, 'task-1', 0)['task_id'] == 'task-1'


def test_preflight_rejects_existing_rmf_schedule():
    assert existing_rmf_processes([
        ('amcl', '/a200_1060'), ('rmf_traffic_schedule_primary', '/')
    ]) == ['rmf_traffic_schedule_primary']


def test_distributed_preflight_requires_one_laptop_core_and_no_adapter():
    core = [(name, '/') for name in (
        'rmf_traffic_schedule_primary', 'rmf_task_dispatcher',
        'building_map_server')]
    assert rmf_core_errors(core) == []
    assert unexpected_rmf_processes(core, True) == []
    assert len(unexpected_rmf_processes(core, False)) == 3
    assert 'found 0' in rmf_core_errors(core[1:])[0]
    assert 'found 2' in rmf_core_errors(core + core[:1])[0]
    assert unexpected_rmf_processes(core + [('brin_husky_fleet_adapter', '/')],
                                    True) == ['brin_husky_fleet_adapter']


def test_distributed_preflight_rejects_stale_mismatched_or_duplicate_profile():
    assert profile_match_errors('abc', {'abc'}, 10.0, 1, now=12.0) == []
    assert 'differ' in profile_match_errors('abc', {'other'}, 10.0, 1,
                                            now=12.0)[0]
    assert 'stale' in profile_match_errors('abc', {'abc'}, 10.0, 1,
                                           now=16.0)[0]
    assert 'publisher' in profile_match_errors('abc', {'abc'}, 10.0, 2,
                                               now=12.0)[0]


def test_native_controller_probe_is_isolated_and_expires(monkeypatch):
    import brin_husky_hardware.preflight as preflight

    clock = [10.0]
    launched = []

    class CompletedProbe:
        returncode = 0

        def poll(self):
            return self.returncode

        def communicate(self):
            return '{"platform_velocity_controller": "active"}', ''

    def launch(command, **kwargs):
        launched.append((command, kwargs))
        return CompletedProbe()

    monkeypatch.setattr(preflight.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(preflight.subprocess, 'Popen', launch)
    monkeypatch.setenv('CYCLONEDDS_URI', 'file:///tmp/other.xml')
    probe = NativeControllerProbe('/a200_1060/controller_manager/list_controllers',
                                  'rmw_fastrtps_cpp')
    assert probe.poll() is None
    assert launched[0][1]['env']['RMW_IMPLEMENTATION'] == 'rmw_fastrtps_cpp'
    assert 'CYCLONEDDS_URI' not in launched[0][1]['env']
    clock[0] = 11.0
    assert probe.poll() is None
    assert probe.current() == {'platform_velocity_controller': 'active'}
    clock[0] = 27.0
    assert probe.current() is None


def test_launch_only_dispatches_after_preflight(monkeypatch):
    path = ROOT / 'brin_husky_hardware/launch/hardware.launch.py'
    spec = importlib.util.spec_from_file_location('brin_hardware_launch', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'share', lambda name: str(ROOT / name))
    context = LaunchContext()
    description = module.generate_launch_description()
    for entity in description.entities:
        if isinstance(entity, DeclareLaunchArgument):
            entity.execute(context)
    setup = next(e for e in description.entities if isinstance(e, OpaqueFunction))
    handler, bridge, preflight = setup.execute(context)
    assert all(isinstance(e, Node) for e in (bridge, preflight))
    assert isinstance(handler.event_handler.handle(
        SimpleNamespace(returncode=0), context)[0], EmitEvent)
    context.launch_configurations['enable_dispatch'] = 'true'
    assert isinstance(handler.event_handler.handle(
        SimpleNamespace(returncode=1), context)[0], EmitEvent)
    started = handler.event_handler.handle(SimpleNamespace(returncode=0), context)
    assert [node.node_package for node in started] == [
        'rmf_traffic_ros2', 'rmf_task_ros2',
        'rmf_building_map_tools', 'brin_husky_hardware']
    assert all(node.node_package != 'nav2_map_server' for node in started)
    assert all(node.node_package != 'ros_gz_sim' for node in started)
