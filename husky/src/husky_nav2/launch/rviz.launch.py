"""RViz configured for the private Husky Nav2 TF tree."""

import os
import tempfile

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument, EmitEvent, RegisterEventHandler, SetEnvironmentVariable,
)
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitution import Substitution
from launch.substitutions import LaunchConfiguration
from launch.utilities import normalize_to_list_of_substitutions, perform_substitutions
from launch_ros.actions import Node


NS = 'a200_1060'


class ConfigureRviz(Substitution):
    """Apply namespace and display defaults to Nav2's stock RViz config."""

    def __init__(self, source_file, show_rmf_graph):
        super().__init__()
        self._source_file = normalize_to_list_of_substitutions(source_file)
        self._show_rmf_graph = show_rmf_graph

    def describe(self):
        return 'configured Husky Nav2 RViz file'

    def perform(self, context):
        source_path = perform_substitutions(context, self._source_file)
        output = tempfile.NamedTemporaryFile(mode='w', delete=False)
        in_laser_scan = False
        configured_lines = []

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

                configured_lines.append(line)

            config = yaml.safe_load(''.join(configured_lines))
            displays = config['Visualization Manager']['Displays']
            layers = [
                ('RMF scheduled traffic', '/schedule_markers', 'Volatile', 10),
                ('RMF fleet positions', '/fleet_markers', 'Volatile', 10),
            ]
            if self._show_rmf_graph.perform(context) == 'true':
                layers.insert(0, ('RMF navigation graph',
                                  f'/{NS}/rviz/rmf_graph_markers',
                                  'Transient Local', 1))
            existing_topics = {display.get('Topic', {}).get('Value')
                               for display in displays
                               if isinstance(display.get('Topic'), dict)}
            for name, topic, durability, depth in layers:
                if topic not in existing_topics:
                    displays.append({
                        'Class': 'rviz_default_plugins/MarkerArray',
                        'Name': name, 'Enabled': True,
                        'Topic': {'Value': topic, 'Depth': depth,
                                  'Reliability Policy': 'Reliable',
                                  'Durability Policy': durability,
                                  'History Policy': 'Keep Last'},
                    })
            yaml.safe_dump(config, output, sort_keys=False)

        return output.name


def generate_launch_description():
    default_config = os.path.join(
        get_package_share_directory('nav2_bringup'),
        'rviz',
        'nav2_namespaced_view.rviz',
    )
    source_config = LaunchConfiguration('rviz_config')
    rmw_implementation = LaunchConfiguration('rmw_implementation')
    show_rmf_graph = LaunchConfiguration('show_rmf_graph')
    configured_rviz = ConfigureRviz(source_config, show_rmf_graph)
    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='nav2_rviz',
        namespace=NS,
        output='screen',
        arguments=['-d', configured_rviz],
        parameters=[{'use_sim_time': False}],
        remappings=[
            ('/tf', f'/{NS}/nav/tf'),
            ('/tf_static', f'/{NS}/tf_static'),
            ('/initialpose', f'/{NS}/initialpose'),
            ('/goal_pose', f'/{NS}/goal_pose'),
            ('/clicked_point', f'/{NS}/clicked_point'),
        ],
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'rviz_config',
            default_value=default_config,
            description='RViz configuration with <robot_namespace> placeholders',
        ),
        DeclareLaunchArgument(
            'show_rmf_graph', default_value='true', choices=['true', 'false'],
            description='Publish and display the static RMF navigation graph',
        ),
        DeclareLaunchArgument(
            'traffic_profile', default_value='brin_0',
            description='RMF graph profile; must match the map used by Nav2',
        ),
        DeclareLaunchArgument(
            'rmw_implementation',
            default_value='rmw_cyclonedds_cpp',
            description='DDS implementation used by RViz',
        ),
        SetEnvironmentVariable('RMW_IMPLEMENTATION', rmw_implementation),
        Node(
            package='husky_nav2', executable='rmf_graph_markers.py',
            name='rmf_graph_markers', namespace=NS, output='screen',
            parameters=[{'use_sim_time': False,
                         'traffic_profile': LaunchConfiguration('traffic_profile')}],
            condition=IfCondition(show_rmf_graph),
        ),
        RegisterEventHandler(OnProcessExit(
            target_action=rviz,
            on_exit=[EmitEvent(event=Shutdown(reason='RViz closed'))],
        )),
        rviz,
    ])
