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
import yaml

from brin_husky_hardware.adapter import HardwareCommand
from brin_husky_hardware.bridge import (
    PhysicalTfBridge, prefixed_frame, rewrite_transforms, valid_sources)
from brin_husky_hardware.preflight import (
    distance_to_graph, existing_rmf_processes, expected_map, map_geometry_errors,
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
