"""Existing Devi Nav2 stays running; read-only preflight gates dispatch."""
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, OpaqueFunction, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from brin_devi_fleet_adapter.profiles import resolve_profile


def setup(context):
    value = lambda name: LaunchConfiguration(name).perform(context)
    share = Path(get_package_share_directory('brin_devi_fleet_adapter'))
    profile = resolve_profile()
    config = value('integration_config')
    preflight = Node(
        package='brin_devi_fleet_adapter', executable='preflight',
        arguments=['--config', config, '--timeout', value('preflight_timeout')],
        output='screen')
    adapter = Node(
        package='brin_devi_fleet_adapter', executable='fleet_adapter',
        arguments=['--integration-config', config],
        parameters=[{'use_sim_time': False, 'integration_config': config,
                     'fleet_config': value('fleet_config'),
                     'nav_graph': profile['graph'], 'robots': ['devi'],
                     'server_uri': value('server_uri')}],
        remappings=[
            ('/devi/navigate_to_pose', '/navigate_to_pose'),
            ('/devi/backup', '/backup'),
            ('/devi/bt_navigator/get_state', '/bt_navigator/get_state'),
            ('/devi/local_costmap/clear_entirely_local_costmap',
             '/local_costmap/clear_entirely_local_costmap'),
            ('/devi/local_costmap/costmap_raw', '/local_costmap/costmap_raw'),
            ('/devi/sensors/lidar3d_0/scan', '/devi/rplidar/scan_filtered'),
            # Zero stop commands enter the existing smoother, never the motors directly.
            ('/devi/cmd_vel_nav', '/devi/cmd_vel_nav_raw'),
        ], output='screen')

    def after_preflight(event, _context):
        if event.returncode != 0:
            return [EmitEvent(event=Shutdown(reason='Devi preflight failed'))]
        if value('enable_dispatch') != 'true':
            return [EmitEvent(event=Shutdown(reason='Devi preflight passed'))]
        return [adapter]

    return [RegisterEventHandler(OnProcessExit(
        target_action=preflight, on_exit=after_preflight)), preflight]


def generate_launch_description():
    share = Path(get_package_share_directory('brin_devi_fleet_adapter'))
    return LaunchDescription([
        DeclareLaunchArgument('integration_config', default_value=str(share/'config/devi.yaml')),
        DeclareLaunchArgument('fleet_config', default_value=str(share/'config/fleet_config.yaml')),
        DeclareLaunchArgument('preflight_timeout', default_value='12.0'),
        DeclareLaunchArgument('enable_dispatch', default_value='false', choices=['true', 'false']),
        DeclareLaunchArgument('server_uri', default_value=''),
        OpaqueFunction(function=setup),
    ])
