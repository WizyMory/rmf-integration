"""Observe Husky, Devi and all RMF fleets; never start core or an adapter."""
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
    radii = yaml.safe_load((package/'config/fleet_visualization.yaml').read_text())['radii']
    fleet_parameters = {name + '_radius': float(radius) for name, radius in radii.items()}
    fleet_parameters[fleet['fleet_name'] + '_radius'] = float(fleet['profile']['footprint'])
    return [
        Node(package='brin_husky_distributed', executable='visualization_tf',
             parameters=[{'use_sim_time': False}],
             condition=IfCondition(LaunchConfiguration('start_tf')), output='screen'),
        Node(package='rmf_visualization_navgraphs', executable='navgraph_visualizer_node',
             parameters=[{**parameters, 'lane_width': 0.12,
                          'waypoint_scale': 2.0, 'text_scale': 2.0,
                          'lane_transparency': 0.7}],
             condition=IfCondition(LaunchConfiguration('start_visualizers')), output='screen'),
        Node(package='rmf_visualization_fleet_states', executable='fleetstates_visualizer_node',
             parameters=[{**parameters, **fleet_parameters}],
             condition=IfCondition(LaunchConfiguration('start_visualizers')), output='screen'),
        Node(package='rmf_visualization_schedule', executable='schedule_visualizer_node',
             parameters=[{**parameters, 'rate': 5.0, 'wait_secs': 60}],
             condition=IfCondition(LaunchConfiguration('start_visualizers')), output='log'),
        Node(package='rviz2', executable='rviz2', name='husky_rmf_rviz',
             namespace='a200_1060', parameters=[{'use_sim_time': False}],
             arguments=['-d', LaunchConfiguration('rviz_config')],
             # Only RViz consumes this merged observation tree. Control TF
             # and sensor topics on both robots remain unchanged.
             remappings=[('/tf', '/rmf_visualization/tf'),
                         ('/tf_static', '/rmf_visualization/tf_static'),
                         ('/initialpose', '/a200_1060/initialpose'),
                         ('/goal_pose', '/a200_1060/goal_pose'),
                         ('/clicked_point', '/a200_1060/clicked_point')],
             condition=IfCondition(LaunchConfiguration('rviz')), output='screen'),
    ]


def generate_launch_description():
    config = (Path(get_package_share_directory('brin_husky_distributed')) /
              'rviz/devi_rmf.rviz')
    return LaunchDescription([
        DeclareLaunchArgument('rviz', default_value='true', choices=['true', 'false']),
        DeclareLaunchArgument('start_visualizers', default_value='true', choices=['true', 'false']),
        DeclareLaunchArgument('start_tf', default_value='true', choices=['true', 'false']),
        DeclareLaunchArgument('rviz_config', default_value=str(config)),
        OpaqueFunction(function=setup),
    ])
