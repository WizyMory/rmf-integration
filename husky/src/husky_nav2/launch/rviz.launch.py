"""RViz configured for the private Husky Nav2 TF tree."""

import os
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable
from launch.substitution import Substitution
from launch.substitutions import LaunchConfiguration
from launch.utilities import normalize_to_list_of_substitutions, perform_substitutions
from launch_ros.actions import Node


NS = 'a200_1060'


class ConfigureRviz(Substitution):
    """Apply namespace and display defaults to Nav2's stock RViz config."""

    def __init__(self, source_file):
        super().__init__()
        self._source_file = normalize_to_list_of_substitutions(source_file)

    def describe(self):
        return 'configured Husky Nav2 RViz file'

    def perform(self, context):
        source_path = perform_substitutions(context, self._source_file)
        output = tempfile.NamedTemporaryFile(mode='w', delete=False)
        in_laser_scan = False

        with open(source_path, encoding='utf-8') as source, output:
            for line in source:
                line = line.replace('<robot_namespace>', f'/{NS}')
                # This indentation is unique to the disabled RobotModel display
                # in Nav2 Humble's stock namespaced RViz configuration.
                if line.rstrip('\n') == '      Enabled: false':
                    line = '      Enabled: true\n'

                if 'Class: rviz_default_plugins/LaserScan' in line:
                    in_laser_scan = True
                elif in_laser_scan and line.strip().startswith('Color:'):
                    indentation = line[:len(line) - len(line.lstrip())]
                    line = f'{indentation}Color: 255; 255; 0\n'
                elif in_laser_scan and line.strip().startswith('Color Transformer:'):
                    indentation = line[:len(line) - len(line.lstrip())]
                    line = f'{indentation}Color Transformer: FlatColor\n'
                    in_laser_scan = False

                output.write(line)

        return output.name


def generate_launch_description():
    default_config = os.path.join(
        get_package_share_directory('nav2_bringup'),
        'rviz',
        'nav2_namespaced_view.rviz',
    )
    source_config = LaunchConfiguration('rviz_config')
    rmw_implementation = LaunchConfiguration('rmw_implementation')
    configured_rviz = ConfigureRviz(source_config)

    return LaunchDescription([
        DeclareLaunchArgument(
            'rviz_config',
            default_value=default_config,
            description='RViz configuration with <robot_namespace> placeholders',
        ),
        DeclareLaunchArgument(
            'rmw_implementation',
            default_value='rmw_cyclonedds_cpp',
            description='DDS implementation used by RViz',
        ),
        SetEnvironmentVariable('RMW_IMPLEMENTATION', rmw_implementation),
        Node(
            package='rviz2',
            executable='rviz2',
            name='nav2_rviz',
            namespace=NS,
            output='screen',
            arguments=['-d', configured_rviz],
            remappings=[
                ('/tf', f'/{NS}/nav/tf'),
                ('/tf_static', f'/{NS}/tf_static'),
                ('/initialpose', f'/{NS}/initialpose'),
                ('/goal_pose', f'/{NS}/goal_pose'),
                ('/clicked_point', f'/{NS}/clicked_point'),
            ],
        ),
    ])
