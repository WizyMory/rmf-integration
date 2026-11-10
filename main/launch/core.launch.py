"""Run the established core with observation publishers on the main computer."""
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, IncludeLaunchDescription, RegisterEventHandler
from launch.conditions import UnlessCondition
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def process_exited(event, context):
    if not context.is_shutdown:
        return [EmitEvent(event=Shutdown(reason=f'Core subprocess exited: {event.process_name}'))]
    return []


def generate_launch_description():
    package = Path(get_package_share_directory('brin_husky_distributed'))
    return LaunchDescription([
        DeclareLaunchArgument('traffic_profile', default_value='gedungWS_0'),
        DeclareLaunchArgument('server_uri', default_value=''),
        DeclareLaunchArgument('rviz', default_value='false', choices=['true', 'false']),
        DeclareLaunchArgument('rviz_config', default_value=''),
        RegisterEventHandler(OnProcessExit(on_exit=process_exited)),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(str(package / 'launch/laptop.launch.py')),
            launch_arguments={name: LaunchConfiguration(name) for name in (
                'traffic_profile', 'server_uri', 'rviz', 'rviz_config')}.items()),
        # The established laptop launch starts these together with RViz.
        # A server without a display still publishes the observation topics.
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(str(package / 'launch/visualization.launch.py')),
            launch_arguments={'rviz': 'false', 'start_visualizers': 'true',
                              'start_tf': 'true'}.items(),
            condition=UnlessCondition(LaunchConfiguration('rviz'))),
    ])
