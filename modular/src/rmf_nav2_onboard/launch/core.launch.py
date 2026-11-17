"""Optional standalone core. Never run alongside another active RMF core."""
import time

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from rmf_nav2_onboard.config import load, site_digest


def setup(context):
    path = LaunchConfiguration('config').perform(context)
    config = load(path)
    if config['rmf']['expected_profile_digest'] != site_digest(config):
        raise RuntimeError('Standalone core requires its own canonical site digest from pin-assets')
    import rclpy
    rclpy.init(args=[], domain_id=config['rmf']['domain_id'])
    probe = rclpy.create_node('rmf_nav2_core_probe')
    try:
        end = time.monotonic()+3
        while time.monotonic()<end:
            rclpy.spin_once(probe, timeout_sec=.05)
        existing = set(probe.get_node_names()) & {'rmf_traffic_schedule_primary', 'rmf_task_dispatcher', 'building_map_server'}
        if existing:
            raise RuntimeError('An RMF core already exists: '+str(sorted(existing)))
    finally:
        probe.destroy_node()
        rclpy.try_shutdown()
    return [
        Node(package='rmf_traffic_ros2', executable='rmf_traffic_schedule',
             name='rmf_traffic_schedule_primary', parameters=[{'use_sim_time': False}], output='screen'),
        Node(package='rmf_task_ros2', executable='rmf_task_dispatcher',
             name='rmf_task_dispatcher', parameters=[{'use_sim_time': False, 'bidding_time_window': 2.}], output='screen'),
        Node(package='rmf_building_map_tools', executable='building_map_server', name='building_map_server',
             arguments=[config['rmf']['building_map']], parameters=[{'use_sim_time': False}], output='screen'),
        Node(package='rmf_nav2_onboard', executable='site_profile', arguments=['--config', path], output='screen'),
    ]


def generate_launch_description():
    return LaunchDescription([DeclareLaunchArgument('config'), OpaqueFunction(function=setup)])
