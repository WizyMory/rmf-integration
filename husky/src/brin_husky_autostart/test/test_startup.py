from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from brin_husky_autostart.startup import load_settings, prepare
from brin_husky_autostart.supervisor import Supervisor, terminate_group

ROOT = Path(__file__).resolve().parents[2]


def settings():
    return load_settings(ROOT/'brin_husky_autostart/config/bringup.yaml')


def test_parking_pose_is_applied_only_to_generated_amcl(tmp_path):
    source = ROOT/'husky_nav2/config/nav2_params.yaml'
    before = source.read_bytes()
    generated = prepare(settings(), source, tmp_path, ROOT/'brin_rmf_maps',
                        hardware_source=ROOT/'brin_husky_distributed/config/husky_0.yaml',
                        fleet_source=ROOT/'brin_husky_distributed/config/fleet_config.yaml')
    actual = yaml.safe_load(Path(generated['params_file']).read_text())
    expected = yaml.safe_load(before)
    expected['amcl']['ros__parameters'].update(
        set_initial_pose=True, always_reset_initial_pose=True,
        initial_pose={'x': 25.885, 'y': -27.303, 'z': 0., 'yaw': -2.877})
    assert actual == expected
    assert source.read_bytes() == before
    assert generated['map'].endswith('/gedungWS_0_rmf.yaml')
    assert generated['server_uri'] == 'ws://192.168.0.141:8000/_internal'
    assert json.loads((tmp_path/'prepared.json').read_text()) == generated
    hardware = yaml.safe_load((ROOT/'brin_husky_distributed/config/husky_0.yaml').read_text())
    hardware['max_graph_distance'] = 1.25
    assert yaml.safe_load(Path(generated['hardware_config']).read_text()) == hardware
    fleet = yaml.safe_load((ROOT/'brin_rmf_maps/maps/gedungWS_0_fleet.yaml').read_text())
    fleet['max_merge_lane_distance'] = 1.25
    assert yaml.safe_load(Path(generated['startup_fleet_config']).read_text()) == fleet


@pytest.mark.parametrize('path,value', [
    (('initial_pose','yaw'), float('nan')),
    (('initial_pose','x'), True),
    (('initial_pose','frame_id'), 'odom'),
    (('traffic_profile',), 'brin_0'),
    (('retry_delay',), 0.),
    (('startup_graph_distance',), 1.26),
    (('server_uri',), 'ws://localhost:8000/_internal')])
def test_rejects_invalid_parking_configuration(tmp_path, path, value):
    config = deepcopy(settings())
    node = config
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    file = tmp_path/'config.yaml'
    file.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError):
        load_settings(file)


class FakeStartup:
    run = Supervisor.run

    def __init__(self, existing=(), scans=0, navigation_only=False):
        self.stopping = False
        self.children = []
        self.settings = settings()
        self.prepared = {'map': '/canonical/map.yaml', 'params_file': '/runtime/nav2.yaml',
                         'server_uri': self.settings['server_uri'],
                         'hardware_config': '/runtime/hardware.yaml',
                         'startup_fleet_config': '/runtime/fleet.yaml'}
        self.events = []
        self.existing, self.scans, self.navigation_only = existing, scans, navigation_only
        self.runtime_dir = '/unused'

    def poll(self):
        pass

    def status(self, stage, detail):
        self.events.append(stage)
        if stage == 'navigation_ready' and self.navigation_only:
            self.stopping = True

    def get_node_names_and_namespaces(self):
        return self.existing

    def count_publishers(self, topic):
        return self.scans if topic == '/a200_1060/scan' else 0

    def wait(self, condition, stage, detail, timeout=None):
        self.events.append('wait:'+stage)
        return True

    def navigation_ready(self):
        return True

    def core_ready(self):
        return True

    def spawn(self, name, command):
        self.events.append((name,command))
        child = SimpleNamespace(poll=lambda: 0)
        self.children.append((name,child))
        if name == 'adapter':
            self.stopping = True
        return child


def fast_clock(monkeypatch):
    now = iter(range(10000))
    monkeypatch.setattr('brin_husky_autostart.supervisor.time.monotonic', lambda: next(now))


def test_boot_orders_sensor_navigation_core_then_preflight_adapter(monkeypatch):
    fast_clock(monkeypatch)
    startup = FakeStartup()
    startup.run()
    launches = [(item[0], item[1]) for item in startup.events if isinstance(item,tuple)]
    assert [name for name,_ in launches] == ['hokuyo','nav2','adapter']
    assert startup.events.index('wait:scan') < startup.events.index(launches[1])
    assert startup.events.index('wait:rmf_core') < startup.events.index(launches[2])
    assert 'start_hokuyo:=false' in launches[1][1]
    assert 'params_file:=/runtime/nav2.yaml' in launches[1][1]
    assert 'start_nav2:=false' in launches[2][1]
    assert 'enable_dispatch:=true' in launches[2][1]
    assert 'robot.launch.py' in launches[2][1]  # Existing preflight gate is retained.


def test_existing_navigation_refused_and_existing_scan_not_duplicated(monkeypatch):
    fast_clock(monkeypatch)
    with pytest.raises(RuntimeError, match='Existing Nav2'):
        FakeStartup(existing=[('amcl','/a200_1060')]).run()
    with pytest.raises(RuntimeError, match='Multiple scan'):
        FakeStartup(scans=2).run()
    startup = FakeStartup(scans=1, navigation_only=True)
    startup.run()
    launches = [item[0] for item in startup.events if isinstance(item,tuple)]
    assert launches == ['nav2']


def test_core_requires_unique_nodes_matching_recent_profile():
    fake = SimpleNamespace(
        get_node_names_and_namespaces=lambda: [(name,'/') for name in (
            'rmf_traffic_schedule_primary','rmf_task_dispatcher','building_map_server')],
        count_publishers=lambda topic: 1, profile_seen=__import__('time').monotonic(),
        digest='same', prepared={'profile_digest':'same'})
    assert Supervisor.core_ready(fake)
    fake.digest='different'
    assert not Supervisor.core_ready(fake)
    fake.digest='same'
    fake.profile_seen-=10
    assert not Supervisor.core_ready(fake)


def test_shutdown_does_not_signal_already_finished_process(monkeypatch):
    monkeypatch.setattr('brin_husky_autostart.supervisor.os.killpg',
                        lambda *a: pytest.fail('finished process must not be signalled'))
    terminate_group(SimpleNamespace(poll=lambda: 0))


@pytest.mark.parametrize('extra', [None, 'shape', 'too_far'])
def test_startup_fleet_override_only_changes_approved_merge_distance(tmp_path, monkeypatch, extra):
    import importlib.util
    from launch import LaunchContext
    from launch_ros.utilities import evaluate_parameters
    from brin_husky_distributed import profiles
    path = ROOT/'brin_husky_distributed/launch/robot.launch.py'
    spec = importlib.util.spec_from_file_location('physical_startup_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'get_package_share_directory', lambda p: str(ROOT/p))
    monkeypatch.setattr(profiles, 'get_package_share_directory', lambda p: str(ROOT/p))
    fleet = yaml.safe_load((ROOT/'brin_rmf_maps/maps/gedungWS_0_fleet.yaml').read_text())
    fleet['max_merge_lane_distance'] = 1.25
    if extra == 'shape':
        fleet['profile']['footprint'] = 0.01
    if extra == 'too_far':
        fleet['max_merge_lane_distance'] = 2.0
    override = tmp_path/'fleet.yaml'
    override.write_text(yaml.safe_dump(fleet))
    ctx = LaunchContext()
    ctx.launch_configurations.update({
        'traffic_profile':'gedungWS_0', 'server_uri':'',
        'hardware_config':str(ROOT/'brin_husky_distributed/config/husky_0.yaml'),
        'startup_fleet_config':str(override), 'start_nav2':'false', 'start_hokuyo':'false',
        'preflight_timeout':'35.0', 'enable_dispatch':'true', 'final_orientation_only':'false'})
    if extra is not None:
        with pytest.raises(ValueError, match='only set the approved'):
            module.setup(ctx)
    else:
        handler, _, _ = module.setup(ctx)
        adapter = handler.event_handler.handle(SimpleNamespace(returncode=0), ctx)[0]
        assert evaluate_parameters(ctx, adapter._Node__parameters)[0]['fleet_config'] == str(override)
