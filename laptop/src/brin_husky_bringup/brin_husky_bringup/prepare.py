"""Generate writable Clearpath setups and apply explicit simulation overrides."""
import argparse
import re
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import yaml
import xacro
from ament_index_python.packages import get_package_share_directory
from clearpath_generator_common.description.generator import DescriptionGenerator
from clearpath_generator_gz.param.generator import GzParamGenerator


def prepare_robot(source, target, simulation_profile='fidelity'):
    if simulation_profile not in ('fast', 'fidelity'):
        raise ValueError('Unknown simulation profile: '+simulation_profile)
    source, target = Path(source), Path(target).resolve()
    config = yaml.safe_load(source.read_text())
    namespace = config['system']['ros2']['namespace']
    if not re.fullmatch(r'husky_[0-9]+', namespace):
        raise ValueError(f'Unexpected robot namespace: {namespace}')
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target/'robot.yaml')
    # Installed Clearpath DescriptionGenerator concatenates filenames directly.
    setup = str(target)+'/'
    DescriptionGenerator(setup).generate()
    GzParamGenerator(setup).generate()
    if simulation_profile == 'fast':
        for bridge_file in (target/'sensors/config').glob('*.yaml'):
            bridges = yaml.safe_load(bridge_file.read_text())
            bridges = [b for b in bridges if b['ros_type_name'] != 'sensor_msgs/msg/PointCloud2'
                       and not b['ros_topic_name'].endswith('/data_raw')]
            for bridge in bridges:
                bridge.update(direction='GZ_TO_ROS', lazy=True,
                              publisher_queue=1, subscriber_queue=1)
            bridge_file.write_text(yaml.safe_dump(bridges, sort_keys=False))
    (target/'simulation_profile').write_text(simulation_profile)
    path = target/'platform/config/control.yaml'
    control = yaml.safe_load(path.read_text())
    drive = control[namespace]['platform_velocity_controller']['ros__parameters']
    drive.update(odom_frame_id=f'{namespace}/odom', base_frame_id=f'{namespace}/base_link',
                 tf_frame_prefix_enable=False, enable_odom_tf=False)
    path.write_text(yaml.safe_dump(control, sort_keys=False))
    path = target/'platform/config/localization.yaml'
    localization = yaml.safe_load(path.read_text())
    localization[namespace]['ekf_node']['ros__parameters'].update(
        odom_frame=f'{namespace}/odom', world_frame=f'{namespace}/odom',
        base_link_frame=f'{namespace}/base_link', map_frame='map', use_sim_time=True)
    path.write_text(yaml.safe_dump(localization, sort_keys=False))
    document = xacro.process_file(str(target/'robot.urdf.xacro'), mappings={
        'is_sim': 'true', 'namespace': namespace,
        'gazebo_controllers': str(target/'platform/config/control.yaml'),
        'use_platform_controllers': 'true', 'use_manipulation_controllers': 'false'})
    robot = ET.fromstring(document.toxml())
    # Keep simulator link/joint names unchanged; RSP supplies the TF prefix.
    # Sensor headers must independently use those same prefixed TF names.
    for gazebo in robot.findall('gazebo'):
        for sensor in gazebo.findall('sensor'):
            frame = sensor.find('ignition_frame_id')
            if frame is None:
                frame = ET.SubElement(sensor, 'ignition_frame_id')
                frame.text = gazebo.get('reference')
            if not frame.text:
                raise ValueError('Sensor has no link frame')
            frame.text = namespace+'/'+frame.text
            if sensor.get('type') == 'gpu_lidar':
                # Simulation-only near-range override; robot.yaml is unchanged.
                sensor.find('lidar/range/min').text = '0.15'
                if simulation_profile == 'fast':
                    overrides = {'update_rate': '10', 'visualize': 'false',
                        'lidar/scan/horizontal/samples': '512',
                        'lidar/scan/vertical/samples': '1',
                        'lidar/scan/vertical/min_angle': '0',
                        'lidar/scan/vertical/max_angle': '0'}
                    for key, value in overrides.items():
                        element = sensor.find(key)
                        if element is None:
                            raise ValueError(f'Generated gpu_lidar missing {key}')
                        element.text = value
        for plugin in list(gazebo.findall('plugin')):
            if 'PosePublisher' in plugin.get('name', ''):
                gazebo.remove(plugin)  # EKF is the sole odom -> base authority.
            for remap in plugin.findall('ros/remapping'):
                if remap.text == '~/cmd_vel_unstamped:=platform/cmd_vel_unstamped':
                    remap.text = '~/cmd_vel_unstamped:=cmd_vel'
                if remap.text in ('/tf:=tf', '/tf_static:=tf_static'):
                    plugin.find('ros').remove(remap)
    ET.indent(robot)
    (target/'robot.sim.urdf').write_text(ET.tostring(robot, encoding='unicode'))
    # Clearpath's supported robot_spawn launch includes these service paths.
    # Reuse its spawning API with our small shared-TF service launch functions.
    for group in ('platform', 'sensors', 'manipulators'):
        directory = target/group/'launch'
        directory.mkdir(parents=True, exist_ok=True)
        (directory/f'{group}-service.launch.py').write_text(
            'from pathlib import Path\n'
            f'from brin_husky_bringup.robot_services import {group}\n'
            'def generate_launch_description():\n'
            f'    return {group}(Path(__file__).resolve().parents[2])\n')
    return target


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--config', type=Path, default=Path(
        get_package_share_directory('brin_husky_bringup'))/'config/robots')
    a = p.parse_args()
    setups = [prepare_robot(source, a.output/source.parent.name)
              for source in sorted(a.config.glob('husky_*/robot.yaml'))]
    if not setups:
        p.error('No robot configurations found')
    combine_controller_parameters(setups)
    for setup in setups:
        print(setup)


def combine_controller_parameters(setups):
    """All plugins share a process; give its global ROS arguments all roots.

    Humble ign_ros2_control mutates process-global parameter arguments. Separate
    YAMLs can cause the earlier robot's controller to receive default values.
    A single file containing all explicit namespace roots avoids that race.
    """
    if not setups:
        return
    combined = {}
    for setup in setups:
        combined.update(yaml.safe_load((Path(setup)/'platform/config/control.yaml').read_text()))
    path = Path(setups[0]).resolve().parent/'controllers.yaml'
    path.write_text(yaml.safe_dump(combined, sort_keys=False))
    for setup in setups:
        target = Path(setup)/'robot.sim.urdf'
        tree = ET.parse(target)
        for plugin in tree.findall('.//plugin'):
            if 'ROS2ControlPlugin' in plugin.get('name', ''):
                plugin.find('parameters').text = str(path)
        tree.write(target, encoding='unicode')
