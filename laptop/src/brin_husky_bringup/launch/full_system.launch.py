from ament_index_python.packages import get_package_share_directory as share
from pathlib import Path
import yaml
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction, RegisterEventHandler, EmitEvent
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch_ros.parameter_descriptions import ParameterValue



def robot_names():
    return sorted(yaml.safe_load((Path(share('brin_rmf_maps'))/'maps/spawns.yaml').read_text()))

def generate_launch_description():
    defaults = {'use_sim_time': 'true', 'rviz': 'true', 'gui': 'true',
                'start_rmf': 'true', 'start_nav2': 'true',
                'setup_root': '', 'server_uri': '', 'use_composition': 'true', 'simulation_profile': 'fast', 'world_file': 'brin.sdf', 'nav2_start_batch_size': '2',
                'rviz_profile': 'light', 'log_level': 'warn',
                # Empty delegates selection to DEFAULT_TRAFFIC_PROFILE in the
                # RMF launch, while an explicit CLI value overrides it.
                'traffic_profile': ''}
    defaults.update({'start_'+name: 'true' for name in robot_names()})
    actions = [DeclareLaunchArgument(name, default_value=value) for name, value in defaults.items()]
    actions.append(DeclareLaunchArgument(
        'rmf_visualization', default_value=LaunchConfiguration('rviz'),
        description='Publish RMF schedule and fleet markers; defaults to the rviz setting'))
    common = {name: LaunchConfiguration(name) for name in ['use_sim_time']+['start_'+robot for robot in robot_names()]}
    def include(package, file, arguments, condition=None):
        return IncludeLaunchDescription(PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare(package), 'launch', file])),
            launch_arguments=arguments.items(), condition=condition)
    components = [
        include('brin_husky_bringup', 'simulation.launch.py',
                dict(common, gui=LaunchConfiguration('gui'), setup_root=LaunchConfiguration('setup_root'), simulation_profile=LaunchConfiguration('simulation_profile'), world_file=LaunchConfiguration('world_file'))),
        include('brin_husky_nav2', 'navigation.launch.py', dict(common, use_composition=LaunchConfiguration('use_composition'),
                    simulation_profile=LaunchConfiguration('simulation_profile'),
                    nav2_start_batch_size=LaunchConfiguration('nav2_start_batch_size'),
                    log_level=LaunchConfiguration('log_level'),
                    traffic_profile=LaunchConfiguration('traffic_profile')),
                IfCondition(LaunchConfiguration('start_nav2'))),
        include('brin_husky_fleet_adapter', 'rmf.launch.py',
                dict(common, server_uri=LaunchConfiguration('server_uri'),
                     traffic_profile=LaunchConfiguration('traffic_profile'),
                     rmf_visualization=LaunchConfiguration('rmf_visualization')),
                IfCondition(LaunchConfiguration('start_rmf'))),
        Node(package='rviz2', executable='rviz2', arguments=['-d', PathJoinSubstitution([
            FindPackageShare('brin_husky_nav2'), 'rviz', ['brin_', LaunchConfiguration('rviz_profile'), '.rviz']])],
            parameters=[{'use_sim_time': ParameterValue(LaunchConfiguration('use_sim_time'), value_type=bool)}],
            condition=IfCondition(LaunchConfiguration('rviz')), output='screen')]
    def start_after_controllers(context):
        enabled = [name for name in robot_names()
                   if LaunchConfiguration('start_'+name).perform(context) == 'true']
        gate = Node(package='brin_husky_bringup', executable='wait_for_controllers',
                    parameters=[{'use_sim_time': True, 'robot_names': ','.join(enabled)}],
                    output='screen')
        def ready(event, context):
            if event.returncode != 0:
                return [EmitEvent(event=Shutdown(reason='Robot controllers did not become active'))]
            if LaunchConfiguration('start_nav2').perform(context) != 'true':
                return components[2:]
            navigation_gate = Node(package='brin_husky_nav2', executable='wait_for_navigation',
                name='all_navigation_readiness', parameters=[{'use_sim_time': True,
                'robot_names': ','.join(enabled), 'timeout': 1260.0}], output='screen')
            def navigation_ready(event, context):
                if event.returncode != 0:
                    return [EmitEvent(event=Shutdown(reason='Navigation did not become ready'))]
                return components[2:]
            return [RegisterEventHandler(OnProcessExit(target_action=navigation_gate,
                    on_exit=navigation_ready)), components[1], navigation_gate]
        return [RegisterEventHandler(OnProcessExit(target_action=gate, on_exit=ready)),
                components[0], gate]
    return LaunchDescription(actions+[OpaqueFunction(function=start_after_controllers)])
