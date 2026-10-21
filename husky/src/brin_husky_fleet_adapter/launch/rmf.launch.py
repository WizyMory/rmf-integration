import yaml
from pathlib import Path
from ament_index_python.packages import get_package_share_directory as share
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def traffic_files(context, maps):
    config = yaml.safe_load((maps/'maps/traffic_profiles.yaml').read_text())
    profiles = config['profiles']
    profile_name = (LaunchConfiguration('traffic_profile').perform(context)
                    or config['default_profile'])
    if profile_name not in profiles:
        available = ', '.join(sorted(profiles))
        raise ValueError(
            f'Unknown traffic_profile [{profile_name}]. Available: {available}')

    profile = profiles[profile_name]
    building_map = maps / 'maps' / profile['building_map']
    nav_graph = maps / 'nav_graphs' / profile['nav_graph']
    nav2_map = maps / 'maps' / profile['nav2_map']
    missing = [str(path) for path in (building_map, nav_graph, nav2_map)
               if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            f'Traffic profile [{profile_name}] is incomplete; missing: '
            + ', '.join(missing))
    return building_map, nav_graph


def launch_setup(context):
    sim = LaunchConfiguration('use_sim_time').perform(context) == 'true'
    server_uri = LaunchConfiguration('server_uri').perform(context)
    maps = Path(share('brin_rmf_maps'))
    package = Path(share('brin_husky_fleet_adapter'))
    building_map, nav_graph = traffic_files(context, maps)
    fleet_config = package/'config/fleet_config.yaml'
    fleet_description = yaml.safe_load(fleet_config.read_text())
    map_name = fleet_description['map_name']
    fleet_radius_parameter = {
        fleet_description['fleet_name']+'_radius':
            float(fleet_description['profile']['footprint'])}
    robots = [name for name in robot_names()
              if LaunchConfiguration('start_'+name).perform(context) == 'true']
    actions = [
        Node(package='rmf_traffic_ros2', executable='rmf_traffic_schedule',
             name='rmf_traffic_schedule_primary', parameters=[{'use_sim_time': sim}], output='screen'),
        Node(package='rmf_task_ros2', executable='rmf_task_dispatcher', name='rmf_task_dispatcher',
             parameters=[{'use_sim_time': sim, 'bidding_time_window': 2.0}], output='screen'),
        Node(package='rmf_building_map_tools', executable='building_map_server', name='building_map_server',
             arguments=[str(building_map)], parameters=[{'use_sim_time': sim}], output='screen')]
    visualize = IfCondition(LaunchConfiguration('rmf_visualization'))
    actions += [
        Node(package='rmf_visualization_schedule',
             executable='schedule_visualizer_node',
             parameters=[{'use_sim_time': sim, 'initial_map_name': map_name}],
             condition=visualize, output='log'),
        Node(package='rmf_visualization_fleet_states',
             executable='fleetstates_visualizer_node',
             parameters=[{'use_sim_time': sim, 'initial_map_name': map_name,
                          **fleet_radius_parameter}],
             condition=visualize, output='screen')]
    if robots:
        actions.append(Node(package='brin_husky_fleet_adapter', executable='fleet_adapter',
             parameters=[{'use_sim_time': sim, 'fleet_config': str(fleet_config),
                          'nav_graph': str(nav_graph), 'robots': robots,
                          'server_uri': server_uri}], output='screen'))
    return actions



def robot_names():
    return sorted(yaml.safe_load((Path(share('brin_rmf_maps'))/'maps/spawns.yaml').read_text()))

def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('server_uri', default_value=''),
        DeclareLaunchArgument('traffic_profile', default_value=''),
        DeclareLaunchArgument('rmf_visualization', default_value='false'),
        *[DeclareLaunchArgument('start_'+name, default_value='true') for name in robot_names()],
        OpaqueFunction(function=launch_setup)])
