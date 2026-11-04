"""Laptop authority: exactly one RMF core and one map/graph announcement."""
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from brin_husky_distributed.profiles import resolve_profile
from brin_husky_distributed.web_runtime import validate_server_uri


def setup(context):
    profile = resolve_profile(LaunchConfiguration('traffic_profile').perform(context))
    server_uri = validate_server_uri(LaunchConfiguration('server_uri').perform(context))
    actions = [
        Node(package='rmf_traffic_ros2', executable='rmf_traffic_schedule',
             name='rmf_traffic_schedule_primary',
             parameters=[{'use_sim_time': False}], output='screen'),
        Node(package='rmf_task_ros2', executable='rmf_task_dispatcher',
             name='rmf_task_dispatcher',
             parameters=[{'use_sim_time': False, 'bidding_time_window': 2.0,
                          'server_uri': server_uri}],
             output='screen'),
        Node(package='rmf_building_map_tools', executable='building_map_server',
             name='building_map_server', arguments=[str(profile['building'])],
             parameters=[{'use_sim_time': False}], output='screen'),
        Node(package='brin_husky_distributed', executable='profile_announcer',
             parameters=[{'use_sim_time': False,
                          'profile_digest': profile['digest']}], output='screen'),
    ]
    if LaunchConfiguration('rviz').perform(context) == 'true':
        chosen_config = LaunchConfiguration('rviz_config').perform(context)
        if not chosen_config:
            filename = 'devi_rmf.rviz' if profile['name'] == 'gedungWS_0' else 'husky_rmf.rviz'
            chosen_config = str(Path(get_package_share_directory('brin_husky_distributed'))/'rviz'/filename)
        visualization = (Path(get_package_share_directory('brin_husky_distributed')) /
                         'launch/visualization.launch.py')
        actions.append(IncludeLaunchDescription(
            PythonLaunchDescriptionSource(str(visualization)),
            launch_arguments={
                'rviz_config': chosen_config,
            }.items()))
    return actions


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('traffic_profile', default_value='banyak_simpangan'),
        DeclareLaunchArgument('server_uri', default_value='',
                              description='Optional local RMF Web internal WebSocket URI'),
        DeclareLaunchArgument('rviz', default_value='false', choices=['true', 'false'],
                              description='Open RMF RViz; gedungWS_0 defaults to Devi manual pose tools'),
        DeclareLaunchArgument('rviz_config', default_value='',
                              description='Optional explicit RViz preset, otherwise selected by traffic profile'),
        OpaqueFunction(function=setup),
    ])
