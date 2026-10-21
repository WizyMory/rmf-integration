"""Laptop authority: exactly one RMF core and one map/graph announcement."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from brin_husky_distributed.profiles import resolve_profile


def setup(context):
    profile = resolve_profile(LaunchConfiguration('traffic_profile').perform(context))
    return [
        Node(package='rmf_traffic_ros2', executable='rmf_traffic_schedule',
             name='rmf_traffic_schedule_primary',
             parameters=[{'use_sim_time': False}], output='screen'),
        Node(package='rmf_task_ros2', executable='rmf_task_dispatcher',
             name='rmf_task_dispatcher',
             parameters=[{'use_sim_time': False, 'bidding_time_window': 2.0}],
             output='screen'),
        Node(package='rmf_building_map_tools', executable='building_map_server',
             name='building_map_server', arguments=[str(profile['building'])],
             parameters=[{'use_sim_time': False}], output='screen'),
        Node(package='brin_husky_distributed', executable='profile_announcer',
             parameters=[{'use_sim_time': False,
                          'profile_digest': profile['digest']}], output='screen'),
    ]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('traffic_profile', default_value='banyak_simpangan'),
        OpaqueFunction(function=setup),
    ])
