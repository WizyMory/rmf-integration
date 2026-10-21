from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    config = os.path.join(
        get_package_share_directory('hokuyo_bringup'),
        'config',
        'hokuyo_params.yaml'
    )

    namespace = 'a200_1060'

    urg_node = Node(
        package='urg_node',
        executable='urg_node_driver',
        name='urg_node',
        namespace=namespace,
        parameters=[config],
        output='screen',
    )

    static_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='hokuyo_static_tf',
        namespace=namespace,
        arguments=['0.265', '0', '0.485', '0', '0', '0', 'base_link', 'laser_frame'],
        remappings=[
            ('/tf', f'/{namespace}/tf'),
            ('/tf_static', f'/{namespace}/tf_static'),
        ],
    )

    return LaunchDescription([urg_node, static_tf])
