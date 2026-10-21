"""Start only the pinned Humble API, using wall time and a separate database."""
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction
from launch.substitutions import LaunchConfiguration

from brin_husky_distributed.web_runtime import web_paths


def setup(context):
    value = lambda name: LaunchConfiguration(name).perform(context)
    python, api = web_paths(value('web_root'))
    runtime = Path(value('runtime_dir')).expanduser().resolve()
    config = (Path(get_package_share_directory('brin_husky_distributed')) /
              'web/api_config.py')
    return [ExecuteProcess(
        cmd=[str(python), '-m', 'api_server'], cwd=str(api), output='screen',
        additional_env={
            'RMF_API_SERVER_CONFIG': str(config),
            'RMF_SERVER_USE_SIM_TIME': 'false',
            'BRIN_WEB_RUNTIME': str(runtime),
            'BRIN_WEB_API_HOST': value('api_host'),
            'BRIN_WEB_PUBLIC_URL': value('public_url'),
        })]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('web_root', description='Path to the pinned rmf-web checkout'),
        DeclareLaunchArgument('runtime_dir',
                              description='Directory for physical-system SQLite and cache'),
        DeclareLaunchArgument('api_host', default_value='127.0.0.1',
                              description='Bind to the laptop LAN IP for the onboard adapter'),
        DeclareLaunchArgument('public_url', default_value='http://localhost:8000',
                              description='API URL as accessed by the laptop browser'),
        OpaqueFunction(function=setup),
    ])
