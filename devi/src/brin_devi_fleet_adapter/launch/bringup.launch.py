"""One Devi Nav2 stack, configured startup localization, and RMF registration."""
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, GroupAction, IncludeLaunchDescription,
                            OpaqueFunction, SetEnvironmentVariable)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from brin_devi_fleet_adapter.startup import prepare_startup
from brin_devi_fleet_adapter.web import configured_server_uri, validate_server_uri


def setup(context):
    value = lambda name: LaunchConfiguration(name).perform(context)
    share = Path(get_package_share_directory('brin_devi_fleet_adapter'))
    server_uri = validate_server_uri(value('server_uri'))
    prepared = prepare_startup(
        share, get_package_share_directory('devi_localization'),
        get_package_share_directory('devi_navigation'), value('runtime_dir'),
        value('integration_config'), value('fleet_config'))
    underlay = Path(get_package_share_directory('devi_bringup'))/'launch/bringup.launch.py'
    return [
        GroupAction(scoped=True, actions=[
            SetEnvironmentVariable('ROS_DOMAIN_ID', '73'),
            SetEnvironmentVariable('RMW_IMPLEMENTATION', 'rmw_fastrtps_cpp'),
            IncludeLaunchDescription(PythonLaunchDescriptionSource(str(underlay)),
                launch_arguments={
                    'localization': 'amcl', 'navigation': 'true', 'rviz': value('rviz'),
                    'map': prepared['map'], 'amcl_params_file': prepared['amcl'],
                    'nav2_params_file': prepared['nav2'],
                }.items()),
        ]),
        Node(package='brin_devi_fleet_adapter', executable='initial_pose_bridge',
             arguments=['--config', prepared['integration']],
             additional_env={'ROS_DOMAIN_ID': '0', 'RMW_IMPLEMENTATION': 'rmw_cyclonedds_cpp'},
             parameters=[{'use_sim_time': False}], respawn=True, respawn_delay=3., output='screen'),
        Node(package='brin_devi_fleet_adapter', executable='adapter_supervisor',
             arguments=['--config', prepared['integration'], '--fleet-config', prepared['fleet'],
                        '--server-uri', server_uri],
             additional_env={'ROS_DOMAIN_ID': '0', 'RMW_IMPLEMENTATION': 'rmw_cyclonedds_cpp'},
             output='screen'),
        Node(package='brin_devi_fleet_adapter', executable='visualization_bridge',
             additional_env={'ROS_DOMAIN_ID': '0', 'RMW_IMPLEMENTATION': 'rmw_cyclonedds_cpp'},
             parameters=[{'use_sim_time': False}], respawn=True, respawn_delay=3., output='screen'),
    ]


def generate_launch_description():
    share = Path(get_package_share_directory('brin_devi_fleet_adapter'))
    return LaunchDescription([
        DeclareLaunchArgument('integration_config', default_value=str(share/'config/devi.yaml')),
        DeclareLaunchArgument('fleet_config', default_value=str(share/'config/fleet_config.yaml')),
        DeclareLaunchArgument('runtime_dir', default_value='/home/devi/rmf-integration/devi/log/bringup_runtime'),
        DeclareLaunchArgument('rviz', default_value='false', choices=['true', 'false']),
        DeclareLaunchArgument('server_uri', default_value=configured_server_uri(share),
                              description='RMF Web endpoint; defaults to config/bringup.yaml'),
        OpaqueFunction(function=setup),
    ])
