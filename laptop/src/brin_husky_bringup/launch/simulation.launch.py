from pathlib import Path
import os
import tempfile
import xml.etree.ElementTree as ET
import yaml
from ament_index_python.packages import get_package_prefix, get_package_share_directory as share
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction, SetEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from brin_husky_bringup.prepare import prepare_robot, combine_controller_parameters


def resolve_world(maps, selected):
    """Select a packaged world by name or an explicit SDF path."""
    choice = Path(selected)
    if not choice.is_absolute():
        if choice.name != selected:
            raise ValueError('world_file must be a packaged SDF filename or an absolute path')
        choice = maps/'worlds'/choice
    if choice.suffix != '.sdf' or not choice.is_file():
        raise ValueError(f'World SDF does not exist: {choice}')
    root = ET.parse(choice).getroot()
    worlds = root.findall('world')
    if root.tag != 'sdf' or len(worlds) != 1 or worlds[0].get('name') != 'brin':
        raise ValueError('Selected SDF must contain exactly one world named brin')
    if worlds[0].find('physics/max_step_size') is None:
        raise ValueError('Selected world requires physics/max_step_size')
    return choice


def launch_setup(context):
    value = lambda name: LaunchConfiguration(name).perform(context)
    if value('use_sim_time') != 'true':
        raise ValueError('Clearpath simulation requires use_sim_time:=true')
    maps = Path(share('brin_rmf_maps'))
    bringup = Path(share('brin_husky_bringup'))
    setup = Path(value('setup_root') or tempfile.mkdtemp(prefix='brin_husky_'))
    spawns = yaml.safe_load((maps/'maps/spawns.yaml').read_text())
    resources = [str(maps/'models')]
    for package in ('clearpath_platform_description', 'clearpath_sensors_description',
                    'clearpath_mounts_description', 'clearpath_manipulators_description'):
        resources.append(str(Path(share(package)).parent))
    resources.append(os.environ.get('IGN_GAZEBO_RESOURCE_PATH', ''))
    actions = [SetEnvironmentVariable('IGN_GAZEBO_RESOURCE_PATH', ':'.join(resources))]
    plugin_paths = [str(Path(get_package_prefix('brin_rmf_maps'))/'lib'),
                    os.environ.get('IGN_GAZEBO_SYSTEM_PLUGIN_PATH', '')]
    actions.append(SetEnvironmentVariable('IGN_GAZEBO_SYSTEM_PLUGIN_PATH', ':'.join(plugin_paths)))
    world = resolve_world(maps, value('world_file'))
    if value('simulation_profile') == 'fast':
        setup.mkdir(parents=True, exist_ok=True)
        tree = ET.parse(world)
        tree.find('.//physics/max_step_size').text = '0.02'
        world = setup/(world.stem+'.fast.sdf')
        tree.write(world, encoding='unicode')
    gz_args = '-r '+('' if value('gui') == 'true' else '-s --headless-rendering ')
    gz_args += '"'+str(world)+'"'
    actions += [IncludeLaunchDescription(PythonLaunchDescriptionSource(
        str(Path(share('ros_gz_sim'))/'launch/gz_sim.launch.py')),
        launch_arguments={'gz_args': gz_args, 'on_exit_shutdown': 'true'}.items()),
        Node(package='ros_gz_bridge', executable='parameter_bridge', name='clock_bridge',
             arguments=['/clock@rosgraph_msgs/msg/Clock[ignition.msgs.Clock'],
             parameters=[{'use_sim_time': True}], output='screen')]
    setups = []
    for name, pose in spawns.items():
        if value('start_'+name) != 'true':
            continue
        target = prepare_robot(bringup/'config/robots'/name/'robot.yaml', setup/name, value('simulation_profile'))
        setups.append(target)
        args = dict(setup_path=str(target)+'/', world='brin', generate='false',
                    use_sim_time='true', rviz='false', z='0.20')
        args.update({key: str(pose[key]) for key in ('x', 'y', 'yaw')})
        actions.append(IncludeLaunchDescription(PythonLaunchDescriptionSource(
            str(Path(share('clearpath_gz'))/'launch/robot_spawn.launch.py')),
            launch_arguments=args.items()))
    combine_controller_parameters(setups)
    return actions



def robot_names():
    return sorted(yaml.safe_load((Path(share('brin_rmf_maps'))/'maps/spawns.yaml').read_text()))

def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('simulation_profile', default_value='fast', choices=['fast', 'fidelity']),
        DeclareLaunchArgument('world_file', default_value='brin.sdf',
            description='Packaged SDF filename (for example brin_dynamic_pedestrian.sdf) or absolute SDF path; world name must be brin'),
        DeclareLaunchArgument('gui', default_value='true'),
        DeclareLaunchArgument('setup_root', default_value='', description='Writable generated setup root; default unique temporary directory'),
        *[DeclareLaunchArgument('start_'+name, default_value='true') for name in robot_names()],
        OpaqueFunction(function=launch_setup)])
