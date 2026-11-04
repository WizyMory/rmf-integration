"""Husky authority: onboard Nav2, physical bridge, preflight, fleet adapter."""
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, EmitEvent, IncludeLaunchDescription,
                            OpaqueFunction, RegisterEventHandler)
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import yaml

from brin_husky_distributed.profiles import resolve_profile
from brin_husky_distributed.web_runtime import validate_server_uri


def setup(context):
    value = lambda name: LaunchConfiguration(name).perform(context)
    server_uri = validate_server_uri(value('server_uri'), remote=True)
    profile = resolve_profile(value('traffic_profile'))
    local_share = Path(get_package_share_directory('brin_husky_distributed'))
    config_path = Path(value('hardware_config'))
    settings = yaml.safe_load(config_path.read_text())
    if settings['robot_name'] != 'husky_0' or settings['ros_namespace'] != 'a200_1060':
        raise ValueError('Only physical /a200_1060 as logical husky_0 is supported')
    if settings['tf_topics'] != ['/a200_1060/nav/tf']:
        raise ValueError('Only /a200_1060/nav/tf is supported by this Husky Nav2 stack')
    fleet_config = profile.get('fleet_config', local_share / 'config/fleet_config.yaml')
    fleet = yaml.safe_load(fleet_config.read_text())
    if fleet['map_name'] != 'L1' or list(fleet['robots']) != ['husky_0']:
        raise ValueError('Physical fleet must contain only husky_0 on L1')

    actions = []
    if value('start_nav2') == 'true':
        nav2_launch = (Path(get_package_share_directory('husky_nav2')) /
                       'launch/navigation.launch.py')
        actions.append(IncludeLaunchDescription(
            PythonLaunchDescriptionSource(str(nav2_launch)),
            launch_arguments={'map': str(profile['map_yaml']),
                              'use_sim_time': 'false',
                              'start_hokuyo': value('start_hokuyo')}.items()))
    bridge = Node(package='brin_husky_hardware', executable='tf_bridge',
                  parameters=[{'use_sim_time': False, 'config_file': str(config_path),
                               'sensor_source_rmw': 'rmw_fastrtps_cpp'}],
                  output='screen')
    preflight = Node(
        package='brin_husky_hardware', executable='preflight',
        parameters=[{'use_sim_time': False, 'config_file': str(config_path),
                     'map_yaml': str(profile['map_yaml']),
                     'nav_graph': str(profile['graph']),
                     'map_name': 'L1', 'timeout': float(value('preflight_timeout')),
                     'allow_rmf_core': True, 'require_rmf_core': True,
                     'controller_probe_rmw': 'rmw_fastrtps_cpp',
                     'profile_digest': profile['digest']}], output='screen')
    ns = settings['ros_namespace']
    remaps = [
        ('/husky_0/navigate_to_pose', f'/{ns}/navigate_to_pose'),
        ('/husky_0/backup', f'/{ns}/backup'),
        ('/husky_0/bt_navigator/get_state', f'/{ns}/bt_navigator/get_state'),
        ('/husky_0/local_costmap/clear_entirely_local_costmap',
         f'/{ns}/local_costmap/clear_entirely_local_costmap'),
        ('/husky_0/local_costmap/costmap_raw', f'/{ns}/local_costmap/costmap_raw'),
        ('/husky_0/sensors/lidar3d_0/scan', '/husky_0/scan'),
        ('/husky_0/cmd_vel_nav', f'/{ns}/cmd_vel_nav'),
    ]
    adapter = Node(
        package='brin_husky_hardware', executable='fleet_adapter',
        name='brin_husky_fleet_adapter',
        parameters=[{'use_sim_time': False, 'fleet_config': str(fleet_config),
                     'nav_graph': str(profile['graph']), 'robots': ['husky_0'],
                     'server_uri': server_uri}],
        remappings=remaps, output='screen')

    def after_preflight(event, _context):
        if event.returncode != 0:
            return [EmitEvent(event=Shutdown(reason='Physical preflight failed'))]
        if value('enable_dispatch') != 'true':
            return [EmitEvent(event=Shutdown(reason='Physical preflight passed'))]
        return [adapter]

    actions.extend([
        RegisterEventHandler(OnProcessExit(
            target_action=preflight, on_exit=after_preflight)),
        bridge, preflight])
    return actions


def generate_launch_description():
    config = (Path(get_package_share_directory('brin_husky_distributed')) /
              'config/husky_0.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('traffic_profile', default_value='banyak_simpangan'),
        DeclareLaunchArgument('hardware_config', default_value=str(config)),
        DeclareLaunchArgument('start_nav2', default_value='false',
                              choices=['true', 'false']),
        DeclareLaunchArgument('start_hokuyo', default_value='false',
                              choices=['true', 'false']),
        DeclareLaunchArgument('preflight_timeout', default_value='180.0'),
        DeclareLaunchArgument('enable_dispatch', default_value='false',
                              choices=['true', 'false']),
        DeclareLaunchArgument('server_uri', default_value=''),
        OpaqueFunction(function=setup),
    ])
