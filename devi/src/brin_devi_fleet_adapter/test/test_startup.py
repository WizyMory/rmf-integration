"""Bringup preparation/waiting logic only; no ROS nodes or robot commands."""
import importlib.util
from pathlib import Path
import pickle
import shutil
import signal
from types import SimpleNamespace

from geometry_msgs.msg import PoseWithCovarianceStamped
from launch import LaunchContext
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription
from launch.utilities import perform_substitutions
from launch_ros.utilities import evaluate_parameters
import pytest
import yaml

from brin_devi_fleet_adapter.initial_pose_bridge import validate_initial_pose
from brin_devi_fleet_adapter.geometry import require_commissioning
from brin_devi_fleet_adapter.profiles import load_settings
from brin_devi_fleet_adapter.startup import prepare_startup
from brin_devi_fleet_adapter import supervisor

PACKAGE = Path(__file__).resolve().parents[1]
DEVI = PACKAGE.parents[1]
REFERENCE = DEVI/'reference/devi_ws/src'


def prepared(tmp_path, overrides=None):
    share = PACKAGE
    if overrides is not None:
        share = tmp_path/'package'
        shutil.copytree(PACKAGE, share, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
        path = share/'config/bringup.yaml'
        startup = yaml.safe_load(path.read_text())
        startup.update(overrides)
        path.write_text(yaml.safe_dump(startup))
    return prepare_startup(share, REFERENCE/'devi_localization',
                           REFERENCE/'devi_navigation', tmp_path/'runtime')


def test_shared_map_automatic_pose_and_confirmed_circle_preserve_underlay(tmp_path):
    sources = [REFERENCE/'devi_localization/config/amcl.yaml',
               REFERENCE/'devi_navigation/config/nav2_indoor.yaml']
    before = [p.read_bytes() for p in sources]
    paths = prepared(tmp_path)
    amcl = yaml.safe_load(Path(paths['amcl']).read_text())
    navigation = yaml.safe_load(Path(paths['nav2']).read_text())
    settings = load_settings(paths['integration'])
    fleet = yaml.safe_load(Path(paths['fleet']).read_text())
    assert amcl['amcl']['ros__parameters']['set_initial_pose'] is True
    assert amcl['amcl']['ros__parameters']['always_reset_initial_pose'] is True
    assert amcl['amcl']['ros__parameters']['initial_pose'] == {
        'x': 19.423, 'y': -28.2408, 'z': 0., 'yaw': 1.83415}
    assert paths['map'].endswith('maps/gedungWS_0_rmf.yaml')
    assert amcl['map_server']['ros__parameters']['yaml_filename'] == settings['nav2_map'] == paths['map']
    assert settings['map_alignment'] == dict(confirmed=True, x=0., y=0., yaw=0.)
    require_commissioning(settings)
    assert fleet['profile']['footprint'] == 0.55
    for costmap in ('local_costmap', 'global_costmap'):
        parameters = navigation[costmap][costmap]['ros__parameters']
        assert parameters['robot_radius'] == 0.55
        assert 'footprint' not in parameters
        assert parameters['use_sim_time'] is False
    old_nav = yaml.safe_load(sources[1].read_text())
    assert navigation['controller_server'] == old_nav['controller_server']
    assert navigation['velocity_smoother'] == old_nav['velocity_smoother']
    assert [p.read_bytes() for p in sources] == before


def test_manual_localization_can_be_restored_without_using_the_old_map_pose(tmp_path):
    paths = prepared(tmp_path, {'localization': 'manual_initial_pose'})
    parameters = yaml.safe_load(Path(paths['amcl']).read_text())['amcl']['ros__parameters']
    assert parameters['set_initial_pose'] is False
    assert parameters['always_reset_initial_pose'] is True
    assert 'initial_pose' not in parameters


@pytest.mark.parametrize('pose', [
    None,
    {'frame_id': 'odom', 'x': 19.423, 'y': -28.2408, 'z': 0., 'yaw': 1.83415},
    {'frame_id': 'map', 'x': True, 'y': -28.2408, 'z': 0., 'yaw': 1.83415},
    {'frame_id': 'map', 'x': float('nan'), 'y': -28.2408, 'z': 0., 'yaw': 1.83415},
    {'frame_id': 'map', 'x': 19.423, 'y': -28.2408, 'z': 0., 'yaw': float('inf')},
    {'frame_id': 'map', 'x': 19.423, 'y': -28.2408, 'z': 0.},
])
def test_automatic_pose_rejects_wrong_frame_or_missing_nonfinite_coordinates(tmp_path, pose):
    with pytest.raises(ValueError, match='Automatic initial pose'):
        prepared(tmp_path, {'initial_pose': pose})
    assert not (tmp_path/'runtime/amcl.yaml').exists()


@pytest.mark.parametrize('radius', [-1., 0., float('nan'), True])
def test_invalid_physical_radius_is_rejected(tmp_path, radius):
    share = tmp_path/'package'
    shutil.copytree(PACKAGE, share, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
    path = share/'config/bringup.yaml'
    data = yaml.safe_load(path.read_text())
    data['footprint_radius'] = radius
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match='radius'):
        prepare_startup(share, REFERENCE/'devi_localization', REFERENCE/'devi_navigation', tmp_path/'runtime')


def test_initial_pose_frame_and_rotation_are_validated():
    pose = PoseWithCovarianceStamped()
    pose.header.frame_id = 'map'
    pose.pose.pose.orientation.w = 1.
    validate_initial_pose(pose)
    assert pickle.loads(pickle.dumps(pose)) == pose
    pose.header.frame_id = 'odom'
    with pytest.raises(ValueError, match='shared map'):
        validate_initial_pose(pose)
    pose.header.frame_id = 'map'
    pose.pose.pose.orientation.w = 0.
    with pytest.raises(ValueError, match='quaternion'):
        validate_initial_pose(pose)


def test_nav2_scope_is_domain_73_and_does_not_change_native_rmf_environment(tmp_path, monkeypatch):
    specification = importlib.util.spec_from_file_location('devi_combined_bringup', PACKAGE/'launch/bringup.launch.py')
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    shares = {'brin_devi_fleet_adapter': PACKAGE, 'devi_localization': REFERENCE/'devi_localization',
              'devi_navigation': REFERENCE/'devi_navigation', 'devi_bringup': REFERENCE/'devi_bringup'}
    monkeypatch.setattr(module, 'get_package_share_directory', lambda name: str(shares[name]))
    context = LaunchContext()
    context.launch_configurations.update(integration_config=str(PACKAGE/'config/devi.yaml'),
        fleet_config=str(PACKAGE/'config/fleet_config.yaml'), runtime_dir=str(tmp_path), rviz='false',
        server_uri='ws://192.168.0.250:8000/_internal')
    context.environment['ROS_DOMAIN_ID'] = '0'
    context.environment['RMW_IMPLEMENTATION'] = 'rmw_cyclonedds_cpp'
    group, bridge, waiting, visualization = module.setup(context)
    assert isinstance(group, GroupAction)
    includes = []
    for action in group.execute(context):
        if isinstance(action, IncludeLaunchDescription):
            includes.append(action)
            assert context.environment['ROS_DOMAIN_ID'] == '73'
            assert context.environment['RMW_IMPLEMENTATION'] == 'rmw_fastrtps_cpp'
        else:
            action.execute(context)
    assert len(includes) == 1
    assert context.environment['ROS_DOMAIN_ID'] == '0'
    assert context.environment['RMW_IMPLEMENTATION'] == 'rmw_cyclonedds_cpp'
    assert bridge.node_executable == 'initial_pose_bridge'
    assert waiting.node_executable == 'adapter_supervisor'
    arguments = [perform_substitutions(context, part) for part in waiting.cmd[1:]]
    assert arguments[arguments.index('--server-uri')+1] == 'ws://192.168.0.250:8000/_internal'
    assert visualization.node_executable == 'visualization_bridge'
    assert evaluate_parameters(context, bridge._Node__parameters)[0]['use_sim_time'] is False
    declaration, = [action for action in module.generate_launch_description().entities
        if isinstance(action, DeclareLaunchArgument) and action.name == 'server_uri']
    assert perform_substitutions(context, declaration.default_value) == 'ws://192.168.0.218:8000/_internal'


@pytest.mark.parametrize('server_uri', ['', 'ws://192.168.0.218:8000/_internal'])
def test_supervisor_waits_for_preflight_before_starting_adapter(tmp_path, monkeypatch, server_uri):
    paths = prepared(tmp_path)
    handlers, calls, stopped = {}, [], []

    def set_signal(number, handler):
        previous = handlers.get(number, signal.SIG_DFL)
        handlers[number] = handler
        return previous

    class Child:
        def __init__(self, code):
            self.returncode = code

        def poll(self):
            if self.returncode is None:
                handlers[signal.SIGTERM](signal.SIGTERM, None)
            return self.returncode

    def spawn(command, **kwargs):
        calls.append((command, kwargs))
        if command[0].endswith('/preflight'):
            return Child(2 if len(calls) == 1 else 0)
        return Child(None)

    monkeypatch.setattr(supervisor.signal, 'signal', set_signal)
    monkeypatch.setattr(supervisor, 'get_package_prefix', lambda name: '/test/install')
    monkeypatch.setattr(supervisor.subprocess, 'Popen', spawn)
    monkeypatch.setattr(supervisor, 'terminate_group', stopped.append)
    clock = [0.]
    monkeypatch.setattr(supervisor.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(supervisor.time, 'sleep', lambda delay: clock.__setitem__(0, clock[0]+delay))
    supervisor.main(['--config', paths['integration'], '--fleet-config', paths['fleet'], '--retry-delay', '1', '--server-uri', server_uri])
    assert len(calls) == 3
    assert all(command[0].endswith('/preflight') for command, _ in calls[:2])
    assert calls[2][0][:4] == ['ros2', 'launch', 'brin_devi_fleet_adapter', 'robot.launch.py']
    assert 'enable_dispatch:=true' in calls[2][0]
    assert not any(argument.endswith(':=') for argument in calls[2][0])
    assert ('server_uri:=' + server_uri in calls[2][0]) == bool(server_uri)
    assert calls[2][1]['env']['ROS_DOMAIN_ID'] == '0'
    assert calls[2][1]['env']['RMW_IMPLEMENTATION'] == 'rmw_cyclonedds_cpp'
    assert stopped
