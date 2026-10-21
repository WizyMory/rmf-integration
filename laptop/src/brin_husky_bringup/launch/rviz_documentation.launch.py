"""Launch the BRIN map and documentation markers without Gazebo or robots."""
from pathlib import Path

from ament_index_python.packages import get_package_share_directory as share
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import yaml


def launch_setup(context):
    profile_name = LaunchConfiguration('traffic_profile').perform(context)
    maps = Path(share('brin_rmf_maps'))
    profiles = yaml.safe_load((maps/'maps/traffic_profiles.yaml').read_text())
    if profile_name not in profiles['profiles']:
        available = ', '.join(sorted(profiles['profiles']))
        raise ValueError(
            f'Unknown traffic_profile [{profile_name}]. Available: {available}')
    map_yaml = maps/'maps'/profiles['profiles'][profile_name]['nav2_map']
    rviz_config = Path(share('brin_husky_bringup'))/'rviz/brin_obstacles.rviz'
    parameters = {'use_sim_time': True}
    return [
        Node(package='nav2_map_server', executable='map_server', name='map_server',
             parameters=[{**parameters, 'yaml_filename': str(map_yaml),
                          'frame_id': 'map'}], output='screen'),
        Node(package='nav2_lifecycle_manager', executable='lifecycle_manager',
             name='lifecycle_manager_documentation_map',
             parameters=[{**parameters, 'autostart': True,
                          'node_names': ['map_server']}], output='screen'),
        Node(package='brin_husky_bringup', executable='publish_documentation_markers',
             parameters=[{**parameters, 'traffic_profile': profile_name}],
             output='screen'),
        Node(package='rviz2', executable='rviz2', arguments=['-d', str(rviz_config)],
             parameters=[parameters], condition=IfCondition(LaunchConfiguration('rviz')),
             output='screen')]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('traffic_profile', default_value='banyak_simpangan'),
        DeclareLaunchArgument('rviz', default_value='true'),
        OpaqueFunction(function=launch_setup)])
