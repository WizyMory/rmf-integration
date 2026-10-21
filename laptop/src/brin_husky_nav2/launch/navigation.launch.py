from pathlib import Path
import tempfile
import yaml
from ament_index_python.packages import get_package_share_directory as share
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, RegisterEventHandler, EmitEvent
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, ComposableNodeContainer
from launch_ros.descriptions import ComposableNode
from brin_husky_nav2.parameters import robot_parameters


def traffic_map(context, maps):
    config = yaml.safe_load((maps/'maps/traffic_profiles.yaml').read_text())
    profiles = config['profiles']
    name = (LaunchConfiguration('traffic_profile').perform(context)
            or config['default_profile'])
    if name not in profiles:
        available = ', '.join(sorted(profiles))
        raise ValueError(f'Unknown traffic_profile [{name}]. Available: {available}')
    path = maps/'maps'/profiles[name]['nav2_map']
    if not path.is_file():
        raise FileNotFoundError(
            f'Traffic profile [{name}] is missing Nav2 map: {path}')
    return path


def launch_setup(context):
    value = lambda n: LaunchConfiguration(n).perform(context)
    sim = value('use_sim_time') == 'true'
    maps, package = Path(share('brin_rmf_maps')), Path(share('brin_husky_nav2'))
    map_yaml = traffic_map(context, maps)
    actions = []
    if value('start_map_server') == 'true':
        actions += [Node(package='nav2_map_server', executable='map_server', name='map_server',
                         parameters=[{'use_sim_time': sim, 'yaml_filename': str(map_yaml),
                                      'frame_id': 'map'}], output='screen'),
                    Node(package='nav2_lifecycle_manager', executable='lifecycle_manager',
                         name='lifecycle_manager_map', parameters=[{'use_sim_time': sim,
                         'autostart': True, 'node_names': ['map_server']}])]
    active = []
    stages = []
    batch = []
    batch_names = []
    batch_size = int(value('nav2_start_batch_size'))
    if not 1 <= batch_size <= 3:
        raise ValueError('nav2_start_batch_size must be 1, 2 or 3')
    enabled = [n for n in robot_names() if value('start_'+n) == 'true']
    for ns in robot_names():
        if value('start_'+ns) != 'true':
            continue
        active.append(ns)
        robot_actions = []
        with tempfile.NamedTemporaryFile(mode='w', prefix=ns+'_nav2_', suffix='.yaml', delete=False) as f:
            yaml.safe_dump(robot_parameters(package/'config/nav2.yaml', ns, sim, value('simulation_profile')), f)
            params = f.name
        nodes = [('nav2_amcl', 'amcl'), ('nav2_controller', 'controller_server'),
                 ('nav2_planner', 'planner_server'), ('nav2_smoother', 'smoother_server'),
                 ('nav2_behaviors', 'behavior_server'), ('nav2_bt_navigator', 'bt_navigator'),
                 ('nav2_waypoint_follower', 'waypoint_follower'),
                 ('nav2_velocity_smoother', 'velocity_smoother')]
        components = []
        plugins = ['nav2_amcl::AmclNode', 'nav2_controller::ControllerServer',
                   'nav2_planner::PlannerServer', 'nav2_smoother::SmootherServer',
                   'behavior_server::BehaviorServer', 'nav2_bt_navigator::BtNavigator',
                   'nav2_waypoint_follower::WaypointFollower', 'nav2_velocity_smoother::VelocitySmoother']
        for (pkg, executable), plugin in zip(nodes, plugins):
            remaps = [('map', '/map')]
            if executable in ('controller_server', 'behavior_server'):
                remaps.append(('cmd_vel', 'cmd_vel_nav'))
            if executable == 'velocity_smoother':
                remaps += [('cmd_vel', 'cmd_vel_nav'), ('cmd_vel_smoothed', 'cmd_vel')]
            if value('use_composition') == 'true':
                components.append(ComposableNode(package=pkg, plugin=plugin, name=executable,
                                  namespace=ns, parameters=[params], remappings=remaps))
            else:
                robot_actions.append(Node(package=pkg, executable=executable, name=executable,
                                    namespace=ns, parameters=[params], remappings=remaps, output='screen'))
        lifecycle_params = [{'use_sim_time': sim, 'autostart': True,
                             'node_names': [exe for _, exe in nodes], 'bond_timeout': 10.0}]
        if components:
            components.append(ComposableNode(package='nav2_lifecycle_manager',
                plugin='nav2_lifecycle_manager::LifecycleManager', namespace=ns,
                name='lifecycle_manager_navigation', parameters=lifecycle_params))
            robot_actions.append(ComposableNodeContainer(package='rclcpp_components',
                executable='component_container_isolated', name='nav2_container', namespace=ns,
                parameters=[params], composable_node_descriptions=components, output='screen',
                arguments=['--ros-args', '--log-level', value('log_level')]))
        else:
            robot_actions.append(Node(package='nav2_lifecycle_manager', executable='lifecycle_manager',
                namespace=ns, name='lifecycle_manager_navigation', parameters=lifecycle_params))
        batch.extend(robot_actions)
        batch_names.append(ns)
        if len(batch_names) == batch_size or ns == enabled[-1]:
            gate = Node(package='brin_husky_nav2', executable='wait_for_navigation',
                        name='readiness_'+batch_names[0],
                        parameters=[{'use_sim_time': sim, 'robot_names': ','.join(batch_names)}],
                        output='screen')
            stages.append((batch, gate))
            batch, batch_names = [], []
    for index, (robot_actions, gate) in enumerate(stages):
        following = stages[index+1][0]+[stages[index+1][1]] if index+1 < len(stages) else []
        def ready(event, context, following=following):
            if event.returncode != 0:
                return [EmitEvent(event=Shutdown(reason='Nav2 readiness failed'))]
            return following
        actions.append(RegisterEventHandler(OnProcessExit(target_action=gate, on_exit=ready)))
    if stages:
        actions += stages[0][0]+[stages[0][1]]
    if active:
        actions.append(Node(package='brin_husky_nav2', executable='initial_pose_manager',
                            parameters=[{'use_sim_time': sim, 'robots': active,
                                         'spawns': str(maps/'maps/spawns.yaml')}], output='screen'))
    return actions



def robot_names():
    return sorted(yaml.safe_load((Path(share('brin_rmf_maps'))/'maps/spawns.yaml').read_text()))

def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('start_map_server', default_value='true'),
        DeclareLaunchArgument('simulation_profile', default_value='fast', choices=['fast', 'fidelity']),
        DeclareLaunchArgument('nav2_start_batch_size', default_value='2', choices=['1', '2', '3']),
        DeclareLaunchArgument('log_level', default_value='warn', choices=['warn', 'info', 'debug']),
        DeclareLaunchArgument('use_composition', default_value='true'),
        DeclareLaunchArgument('traffic_profile', default_value=''),
        *[DeclareLaunchArgument('start_'+name, default_value='true') for name in robot_names()],
        OpaqueFunction(function=launch_setup)])
