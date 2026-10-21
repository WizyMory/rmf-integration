"""One physical Husky: inspect first, then optionally start RMF dispatch."""
from pathlib import Path

from ament_index_python.packages import get_package_share_directory as share
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, EmitEvent, OpaqueFunction,
                            RegisterEventHandler)
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import yaml


def hardware_files(traffic_profile):
    maps = Path(share('brin_rmf_maps'))
    profiles = yaml.safe_load((maps / 'maps/traffic_profiles.yaml').read_text())
    name = traffic_profile or profiles['default_profile']
    if name not in profiles['profiles']:
        raise ValueError(f'Unknown traffic_profile: {name}')
    entry = profiles['profiles'][name]
    paths = (maps / 'maps' / entry['building_map'],
             maps / 'nav_graphs' / entry['nav_graph'],
             maps / 'maps' / entry['nav2_map'])
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    return paths


def launch_setup(context):
    value = lambda name: LaunchConfiguration(name).perform(context)
    config_path = Path(value('hardware_config'))
    config = yaml.safe_load(config_path.read_text())
    if config['robot_name'] != 'husky_0':
        raise ValueError('Only logical RMF robot husky_0 is enabled')
    namespace = config['ros_namespace']
    if not namespace or '/' in namespace:
        raise ValueError('ros_namespace must be one ROS namespace segment')
    building_map, nav_graph, map_yaml = hardware_files(value('traffic_profile'))
    adapter_share = Path(share('brin_husky_fleet_adapter'))
    fleet_config = adapter_share / 'config/fleet_config.yaml'
    fleet = yaml.safe_load(fleet_config.read_text())
    if fleet['map_name'] != 'L1':
        raise ValueError('Hardware map and fleet must both use L1')

    bridge = Node(
        package='brin_husky_hardware', executable='tf_bridge',
        parameters=[{'use_sim_time': False, 'config_file': str(config_path)}],
        output='screen')
    preflight = Node(
        package='brin_husky_hardware', executable='preflight',
        parameters=[{'use_sim_time': False, 'config_file': str(config_path),
                     'map_yaml': str(map_yaml), 'nav_graph': str(nav_graph),
                     'map_name': fleet['map_name'],
                     'timeout': float(value('preflight_timeout'))}],
        output='screen')
    remaps = [
        (f'/husky_0/navigate_to_pose', f'/{namespace}/navigate_to_pose'),
        (f'/husky_0/backup', f'/{namespace}/backup'),
        (f'/husky_0/bt_navigator/get_state', f'/{namespace}/bt_navigator/get_state'),
        (f'/husky_0/local_costmap/clear_entirely_local_costmap',
         f'/{namespace}/local_costmap/clear_entirely_local_costmap'),
        (f'/husky_0/local_costmap/costmap_raw',
         f'/{namespace}/local_costmap/costmap_raw'),
        (f'/husky_0/sensors/lidar3d_0/scan', '/husky_0/scan'),
        (f'/husky_0/cmd_vel_nav', f'/{namespace}/cmd_vel_nav'),
    ]
    server_uri = value('server_uri')
    rmf_actions = [
        Node(package='rmf_traffic_ros2', executable='rmf_traffic_schedule',
             name='rmf_traffic_schedule_primary',
             parameters=[{'use_sim_time': False}], output='screen'),
        Node(package='rmf_task_ros2', executable='rmf_task_dispatcher',
             name='rmf_task_dispatcher',
             parameters=[{'use_sim_time': False, 'bidding_time_window': 2.0}],
             output='screen'),
        Node(package='rmf_building_map_tools', executable='building_map_server',
             name='building_map_server', arguments=[str(building_map)],
             parameters=[{'use_sim_time': False}], output='screen'),
        Node(package='brin_husky_hardware', executable='fleet_adapter',
             parameters=[{'use_sim_time': False, 'fleet_config': str(fleet_config),
                          'nav_graph': str(nav_graph), 'robots': ['husky_0'],
                          'server_uri': server_uri}],
             remappings=remaps, output='screen'),
    ]

    def after_preflight(event, _context):
        if event.returncode != 0:
            return [EmitEvent(event=Shutdown(reason='Physical preflight failed'))]
        if value('enable_dispatch') != 'true':
            return [EmitEvent(event=Shutdown(reason='Physical preflight passed'))]
        return rmf_actions

    return [RegisterEventHandler(OnProcessExit(
                target_action=preflight, on_exit=after_preflight)),
            bridge, preflight]


def generate_launch_description():
    default_config = str(Path(share('brin_husky_hardware')) / 'config/husky_0.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('hardware_config', default_value=default_config),
        DeclareLaunchArgument('traffic_profile', default_value=''),
        DeclareLaunchArgument('preflight_timeout', default_value='45.0'),
        DeclareLaunchArgument('enable_dispatch', default_value='false'),
        DeclareLaunchArgument('server_uri', default_value=''),
        OpaqueFunction(function=launch_setup),
    ])
