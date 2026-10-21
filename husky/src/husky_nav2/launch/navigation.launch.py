"""Hokuyo + fused navigation EKF + AMCL + Nav2 for the A200-1060.

Clearpath starts the platform and twist_mux. A separate EKF fuses the robot's
wheel odometry and IMU without replacing Clearpath's own EKF.
"""

import os

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction,
    SetEnvironmentVariable, TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.descriptions import ParameterFile
from nav2_common.launch import RewrittenYaml


NS = 'a200_1060'
NAV_TF = f'/{NS}/nav/tf'
TF_REMAPS = [('/tf', NAV_TF), ('/tf_static', f'/{NS}/tf_static')]
NAV_CMD = f'/{NS}/cmd_vel_nav'
PLATFORM_CMD = f'/{NS}/cmd_vel'


def _check_map(context, *args, **kwargs):
    path = LaunchConfiguration('map').perform(context)
    if not os.path.isfile(path):
        raise RuntimeError(f'Nav2 map YAML tidak ditemukan: {path}')
    with open(path, encoding='utf-8') as stream:
        metadata = yaml.safe_load(stream)
    if not isinstance(metadata, dict):
        raise RuntimeError(f'Nav2 map YAML tidak valid: {path}')
    resolution = metadata.get('resolution')
    origin = metadata.get('origin')
    image = metadata.get('image')
    if not isinstance(resolution, (int, float)) or resolution <= 0:
        raise RuntimeError('Map memerlukan resolution positif dalam meter/piksel.')
    if not isinstance(origin, list) or len(origin) != 3:
        raise RuntimeError('Map memerlukan origin [x, y, yaw].')
    if not isinstance(image, str):
        raise RuntimeError('Map memerlukan path image.')
    image_path = image if os.path.isabs(image) else os.path.join(os.path.dirname(path), image)
    if not os.path.isfile(image_path):
        raise RuntimeError(f'Image map tidak ditemukan: {image_path}')
    return []


def generate_launch_description():
    package_share = get_package_share_directory('husky_nav2')
    map_default = os.path.join(package_share, 'maps', 'banyak_simpangan_nav2.yaml')
    params_default = os.path.join(package_share, 'config', 'nav2_params.yaml')
    ekf_default = os.path.join(package_share, 'config', 'ekf_params.yaml')

    map_file = LaunchConfiguration('map')
    params_file = LaunchConfiguration('params_file')
    ekf_params_file = LaunchConfiguration('ekf_params_file')
    use_sim_time = LaunchConfiguration('use_sim_time')
    autostart = LaunchConfiguration('autostart')
    navigation = LaunchConfiguration('navigation')
    start_hokuyo = LaunchConfiguration('start_hokuyo')
    rmw_implementation = LaunchConfiguration('rmw_implementation')

    configured_params = ParameterFile(
        RewrittenYaml(
            source_file=params_file,
            root_key=NS,
            param_rewrites={'use_sim_time': use_sim_time},
            convert_types=True,
        ),
        allow_substs=True,
    )
    configured_ekf_params = ParameterFile(
        RewrittenYaml(
            source_file=ekf_params_file,
            root_key=NS,
            param_rewrites={'use_sim_time': use_sim_time},
            convert_types=True,
        ),
        allow_substs=True,
    )

    def nav_node(package, executable, name, remappings=None):
        return Node(
            package=package,
            executable=executable,
            name=name,
            namespace=NS,
            output='screen',
            parameters=[configured_params],
            remappings=TF_REMAPS + (remappings or []),
            condition=IfCondition(navigation),
        )

    return LaunchDescription([
        DeclareLaunchArgument('map', default_value=map_default,
                              description='Absolute path to ROS occupancy-map YAML'),
        DeclareLaunchArgument('params_file', default_value=params_default),
        DeclareLaunchArgument('ekf_params_file', default_value=ekf_default),
        DeclareLaunchArgument('use_sim_time', default_value='false', choices=['true', 'false']),
        DeclareLaunchArgument('autostart', default_value='true', choices=['true', 'false']),
        DeclareLaunchArgument('navigation', default_value='true', choices=['true', 'false'],
                              description='Set false to test map_server and AMCL only'),
        DeclareLaunchArgument('start_hokuyo', default_value='true', choices=['true', 'false'],
                              description='Set false only when /a200_1060/scan is already running'),
        DeclareLaunchArgument('rmw_implementation', default_value='rmw_cyclonedds_cpp',
                              description='DDS implementation for Nav2 and optional Hokuyo nodes'),
        SetEnvironmentVariable('RMW_IMPLEMENTATION', rmw_implementation),
        OpaqueFunction(function=_check_map),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(
                get_package_share_directory('hokuyo_bringup'),
                'launch', 'hokuyo_bringup.launch.py')),
            condition=IfCondition(start_hokuyo),
        ),
        Node(
            package='robot_localization', executable='ekf_node',
            name='nav_ekf_node', namespace=NS, output='screen',
            parameters=[configured_ekf_params],
            remappings=TF_REMAPS + [('odometry/filtered', 'nav/odom/filtered')],
        ),
        Node(
            package='husky_nav2', executable='wheel_tf_relay.py',
            name='wheel_tf_relay', namespace=NS, output='screen',
        ),
        Node(
            package='nav2_map_server', executable='map_server', name='map_server',
            namespace=NS, output='screen',
            parameters=[configured_params, {'yaml_filename': map_file}],
            remappings=TF_REMAPS,
        ),
        Node(
            package='nav2_amcl', executable='amcl', name='amcl',
            namespace=NS, output='screen',
            parameters=[configured_params], remappings=TF_REMAPS,
        ),
        Node(
            package='nav2_lifecycle_manager', executable='lifecycle_manager',
            name='lifecycle_manager_localization', namespace=NS, output='screen',
            parameters=[{'use_sim_time': use_sim_time, 'autostart': autostart,
                         'node_names': ['map_server', 'amcl']}],
        ),
        nav_node('nav2_controller', 'controller_server', 'controller_server',
                 [('cmd_vel', NAV_CMD)]),
        nav_node('nav2_smoother', 'smoother_server', 'smoother_server'),
        nav_node('nav2_planner', 'planner_server', 'planner_server'),
        nav_node('nav2_behaviors', 'behavior_server', 'behavior_server',
                 [('cmd_vel', NAV_CMD)]),
        nav_node('nav2_bt_navigator', 'bt_navigator', 'bt_navigator'),
        nav_node('nav2_waypoint_follower', 'waypoint_follower', 'waypoint_follower'),
        nav_node('nav2_velocity_smoother', 'velocity_smoother', 'velocity_smoother',
                 [('cmd_vel', NAV_CMD), ('cmd_vel_smoothed', PLATFORM_CMD)]),
        # Map loading is relatively expensive; let localization configure first.
        TimerAction(
            period=12.0,
            actions=[Node(
                package='nav2_lifecycle_manager', executable='lifecycle_manager',
                name='lifecycle_manager_navigation', namespace=NS, output='screen',
                parameters=[{'use_sim_time': use_sim_time, 'autostart': autostart,
                             'node_names': ['controller_server', 'smoother_server',
                                            'planner_server', 'behavior_server', 'bt_navigator',
                                            'waypoint_follower', 'velocity_smoother']}],
            )],
            condition=IfCondition(navigation),
        ),
    ])
