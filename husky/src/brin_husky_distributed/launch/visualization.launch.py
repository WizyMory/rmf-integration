"""Observe the existing physical Husky and RMF; never start core or an adapter."""
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import yaml


def setup(context):
    package = Path(get_package_share_directory('brin_husky_distributed'))
    fleet = yaml.safe_load((package / 'config/fleet_config.yaml').read_text())
    parameters = {'use_sim_time': False, 'initial_map_name': fleet['map_name']}
    return [
        Node(package='rmf_visualization_navgraphs', executable='navgraph_visualizer_node',
             parameters=[{**parameters, 'lane_width': 0.12,
                          'waypoint_scale': 2.0, 'text_scale': 2.0,
                          'lane_transparency': 0.7}], output='screen'),
        Node(package='rmf_visualization_fleet_states', executable='fleetstates_visualizer_node',
             parameters=[{**parameters, fleet['fleet_name'] + '_radius':
                          float(fleet['profile']['footprint'])}], output='screen'),
        Node(package='rmf_visualization_schedule', executable='schedule_visualizer_node',
             parameters=[{**parameters, 'rate': 5.0, 'wait_secs': 60}], output='log'),
        Node(package='rviz2', executable='rviz2', name='husky_rmf_rviz',
             namespace='a200_1060', parameters=[{'use_sim_time': False}],
             arguments=['-d', LaunchConfiguration('rviz_config')],
             # Same subscriptions as husky_nav2/rviz.launch.py. These remaps
             # only select RViz inputs; no TF publisher or bridge is started.
             remappings=[('/tf', '/a200_1060/nav/tf'),
                         ('/tf_static', '/a200_1060/tf_static'),
                         ('/initialpose', '/a200_1060/initialpose'),
                         ('/goal_pose', '/a200_1060/goal_pose'),
                         ('/clicked_point', '/a200_1060/clicked_point')],
             condition=IfCondition(LaunchConfiguration('rviz')), output='screen'),
    ]


def generate_launch_description():
    config = (Path(get_package_share_directory('brin_husky_distributed')) /
              'rviz/husky_rmf.rviz')
    return LaunchDescription([
        DeclareLaunchArgument('rviz', default_value='true', choices=['true', 'false']),
        DeclareLaunchArgument('rviz_config', default_value=str(config)),
        OpaqueFunction(function=setup),
    ])
