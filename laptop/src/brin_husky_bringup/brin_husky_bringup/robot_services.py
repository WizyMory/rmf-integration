"""ROS-native Clearpath controllers/EKF, shared TF, generated sensor bridges."""
import yaml
from launch import LaunchDescription
from launch_ros.actions import Node


def namespace(setup):
    return yaml.safe_load((setup/'robot.yaml').read_text())['system']['ros2']['namespace']


def platform(setup):
    ns = namespace(setup)
    return LaunchDescription([
        Node(package='robot_state_publisher', executable='robot_state_publisher',
             namespace=ns, name='robot_state_publisher', output='screen', parameters=[{
                 'robot_description': (setup/'robot.sim.urdf').read_text(),
                 'frame_prefix': ns+'/', 'use_sim_time': True}],
             remappings=[('joint_states', 'platform/joint_states')]),
        Node(package='brin_husky_bringup', executable='serialized_spawner', namespace=ns,
             arguments=['--lock-file', str(setup.parent/'controller_loading.lock'),
                        'joint_state_broadcaster', 'platform_velocity_controller',
                        '--param-file', str(setup/'platform/config/control.yaml'),
                        '--controller-manager', '/'+ns+'/controller_manager',
                        '--controller-manager-timeout', '120', '--switch-timeout', '30'],
             parameters=[{'use_sim_time': True}], output='screen'),
        Node(package='robot_localization', executable='ekf_node', name='ekf_node',
             namespace=ns, parameters=[str(setup/'platform/config/localization.yaml')],
             remappings=[('odometry/filtered', 'platform/odom/filtered')], output='screen'),
    ])


def sensors(setup):
    ns = namespace(setup)
    qos = {}
    if (setup/'simulation_profile').read_text() == 'fast':
        for path in (setup/'sensors/config').glob('*.yaml'):
            for bridge in yaml.safe_load(path.read_text()):
                topic = '/'+ns+'/sensors/'+bridge['ros_topic_name']
                qos['qos_overrides.'+topic+'.publisher.reliability'] = 'best_effort'
                qos['qos_overrides.'+topic+'.publisher.depth'] = 1
    return LaunchDescription([
        Node(package='ros_gz_bridge', executable='parameter_bridge',
             namespace=ns+'/sensors', name=path.stem+'_bridge', output='screen',
             parameters=[{'use_sim_time': True, 'config_file': str(path), **qos}])
        for path in sorted((setup/'sensors/config').glob('*.yaml'))
    ])


def manipulators(setup):
    return LaunchDescription([])
