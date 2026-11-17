"""Opt-in loopback smoke test. No physical robot/core endpoints are used."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import pytest
import yaml

from test_module import profile, save
from rmf_nav2_onboard.gateway import Gateway

pytestmark = pytest.mark.skipif(os.environ.get('RMF_NAV2_TEST_ROS') != '1',
                               reason='Opt in to isolated ROS loopback tests with RMF_NAV2_TEST_ROS=1')


@pytest.fixture
def fake_nav2(profile, monkeypatch):
    import rclpy
    from rclpy.context import Context
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.action import ActionServer
    from rclpy.qos import DurabilityPolicy, QoSProfile
    from rcl_interfaces.msg import ParameterValue
    from rcl_interfaces.srv import GetParameters
    from geometry_msgs.msg import TransformStamped
    from lifecycle_msgs.srv import GetState
    from nav2_msgs.action import NavigateToPose
    from nav_msgs.msg import OccupancyGrid, Odometry
    from sensor_msgs.msg import LaserScan
    from tf2_msgs.msg import TFMessage

    path, config = profile
    monkeypatch.setenv('RMW_IMPLEMENTATION', 'rmw_fastrtps_cpp')
    monkeypatch.setenv('ROS_LOCALHOST_ONLY', '1')
    monkeypatch.setenv('ROS_LOG_DIR', str(path.parent/'ros_log'))
    for key in ('ROS_DISCOVERY_SERVER', 'CYCLONEDDS_URI', 'FASTRTPS_DEFAULT_PROFILES_FILE', 'FASTDDS_DEFAULT_PROFILES_FILE'):
        monkeypatch.delenv(key, raising=False)
    for section, domain in [('nav2', 221), ('rmf', 222)]:
        config[section].update(domain_id=domain, rmw='rmw_fastrtps_cpp', localhost_only=True)
    config['commissioning'] = {k: True for k in config['commissioning']}
    save(path, config)
    context = Context()
    rclpy.init(context=context, args=[], domain_id=221)
    node = rclpy.create_node('mock_nav2', context=context)
    executor = SingleThreadedExecutor(context=context)
    executor.add_node(node)
    calls = []
    def execute(goal_handle):
        calls.append(goal_handle)
        goal_handle.abort()
        return NavigateToPose.Result()
    server = ActionServer(node, NavigateToPose, config['nav2']['navigate_action'], execute)
    def state(request, response):
        response.current_state.id = 3
        return response
    def parameter(request, response):
        response.values = [ParameterValue(type=1, bool_value=False) for _ in request.names]
        return response
    services = []
    for name in config['nav2']['lifecycle_nodes']:
        services.extend([node.create_service(GetState, name+'/get_state', state),
                         node.create_service(GetParameters, name+'/get_parameters', parameter)])
    nav = config['nav2']
    publishers = {
        'map': node.create_publisher(OccupancyGrid, nav['map_topic'], QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)),
        'scan': node.create_publisher(LaserScan, nav['scan_topic'], 10),
        'odom': node.create_publisher(Odometry, nav['odom_topic'], 10),
        'tf': node.create_publisher(TFMessage, nav['tf_topic'], 10)}
    def publish():
        stamp = node.get_clock().now().to_msg()
        grid = OccupancyGrid()
        grid.header.frame_id = 'map'
        grid.header.stamp = stamp
        grid.info.width = grid.info.height = 3
        grid.info.resolution = 1.
        grid.info.origin.orientation.w = 1.
        grid.data = [0]*9
        scan = LaserScan()
        scan.header.frame_id, scan.header.stamp = 'laser', stamp
        scan.ranges = [2.]
        odom = Odometry()
        odom.header.frame_id, odom.header.stamp = 'odom', stamp
        transform = TransformStamped()
        transform.header.frame_id, transform.header.stamp = 'map', stamp
        transform.child_frame_id = 'base_link'
        transform.transform.rotation.w = 1.
        for key, message in [('map', grid), ('scan', scan), ('odom', odom), ('tf', TFMessage(transforms=[transform]))]:
            publishers[key].publish(message)
    timer = node.create_timer(.05, publish)
    yield path, config, node, calls, executor
    executor.shutdown()
    server.destroy()
    node.destroy_node()
    context.shutdown()


def test_real_gateway_reads_mock_nav2_in_different_domain_without_goals(fake_nav2):
    import rclpy
    path, config, node, calls, executor = fake_nav2
    gateway = Gateway(config)
    try:
        deadline = time.monotonic()+14
        while time.monotonic()<deadline:
            executor.spin_once(timeout_sec=.02)
            gateway.poll()
            if gateway.fresh and gateway.state.get('nav2_ready'):
                break
        assert gateway.state.get('nav2_ready'), gateway.state
        assert gateway.state['action_servers'] == 1
        assert not calls
        with pytest.raises(RuntimeError, match='Read-only'):
            gateway.send('goal', id='must_not_reach_nav2', pose=[1, 0, 0])
    finally:
        gateway.close()


def test_native_rmf_registers_mock_robot_without_moving(fake_nav2, tmp_path):
    import rclpy
    from rclpy.context import Context
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import DurabilityPolicy, QoSProfile
    from std_msgs.msg import String
    from ament_index_python.packages import get_package_prefix
    path, config, robot_node, calls, robot_executor = fake_nav2
    executable = Path(get_package_prefix('rmf_traffic_ros2'))/'lib/rmf_traffic_ros2/rmf_traffic_schedule'
    env = dict(os.environ, ROS_DOMAIN_ID='222', ROS_LOCALHOST_ONLY='1', RMW_IMPLEMENTATION='rmw_fastrtps_cpp')
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])+os.pathsep+env.get('PYTHONPATH', '')
    context = Context()
    rclpy.init(context=context, args=[], domain_id=222)
    dispatcher = rclpy.create_node('rmf_task_dispatcher', context=context)
    building = rclpy.create_node('building_map_server', context=context)
    profile_node = rclpy.create_node('test_profile', context=context)
    core_executor = SingleThreadedExecutor(context=context)
    for node in (dispatcher, building, profile_node):
        core_executor.add_node(node)
    publisher = profile_node.create_publisher(String, config['rmf']['profile_topic'],
        QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
    timer = profile_node.create_timer(.2, lambda: publisher.publish(String(data='a'*64)))
    schedule_log, adapter_log = tmp_path/'schedule.log', tmp_path/'adapter.log'
    processes = []
    try:
        with schedule_log.open('w') as schedule_stream, adapter_log.open('w') as adapter_stream:
            processes.append(subprocess.Popen([str(executable), '--ros-args', '-r', '__node:=rmf_traffic_schedule_primary'],
                                               env=env, stdout=schedule_stream, stderr=subprocess.STDOUT))
            processes.append(subprocess.Popen(['python3', '-m', 'rmf_nav2_onboard.cli', 'run', '--config', str(path), '--enable-dispatch'],
                                               env=env, stdout=adapter_stream, stderr=subprocess.STDOUT))
            deadline = time.monotonic()+40
            while time.monotonic()<deadline:
                robot_executor.spin_once(timeout_sec=.01)
                core_executor.spin_once(timeout_sec=.01)
                if 'Registered robot_01 in Robot01Fleet' in adapter_log.read_text():
                    break
                if processes[-1].poll() is not None:
                    break
            assert 'Registered robot_01 in Robot01Fleet' in adapter_log.read_text(), adapter_log.read_text()
            assert not calls, 'Registration must not send an idle Nav2 goal'
            processes[-1].send_signal(signal.SIGINT)
            deadline = time.monotonic()+8
            while processes[-1].poll() is None and time.monotonic()<deadline:
                robot_executor.spin_once(timeout_sec=.03)
            assert processes[-1].poll() == 0, adapter_log.read_text()
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        core_executor.shutdown()
        for node in (profile_node, building, dispatcher):
            node.destroy_node()
        context.shutdown()
