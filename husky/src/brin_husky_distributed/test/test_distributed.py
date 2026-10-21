"""The laptop owns RMF core; the robot only dispatches after strict preflight."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from launch import LaunchContext
from launch.actions import EmitEvent, IncludeLaunchDescription
from launch_ros.actions import Node
import yaml

from brin_husky_distributed import profiles
from brin_husky_hardware.preflight import rmf_core_errors


ROOT = Path(__file__).resolve().parents[2]


def load(name, monkeypatch):
    path = ROOT / 'brin_husky_distributed/launch' / (name + '.launch.py')
    spec = importlib.util.spec_from_file_location(name + '_distributed', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(profiles, 'get_package_share_directory',
                        lambda package: str(ROOT / package))
    if name == 'robot':
        monkeypatch.setattr(module, 'get_package_share_directory',
                            lambda package: str(ROOT / package))
    return module


def context(profile='banyak_simpangan', dispatch='false', start_nav2='false'):
    result = LaunchContext()
    result.launch_configurations.update({
        'traffic_profile': profile,
        'hardware_config': str(ROOT / 'brin_husky_distributed/config/husky_0.yaml'),
        'start_nav2': start_nav2,
        'start_hokuyo': 'false',
        'preflight_timeout': '180.0',
        'enable_dispatch': dispatch,
        'server_uri': '',
    })
    return result


def test_profiles_follow_authoritative_manifest_and_hash_all_assets():
    maps = ROOT / 'brin_rmf_maps'
    manifest = yaml.safe_load((maps / 'maps/traffic_profiles.yaml').read_text())
    for name, entry in manifest['profiles'].items():
        result = profiles.resolve_profile(name, maps)
        assert result['graph'].name == entry['nav_graph']
        assert result['map_yaml'].name == entry['nav2_map']
        assert len(result['digest']) == 64
        assert result['digest'] == profiles.resolve_profile(name, maps)['digest']
    assert profiles.resolve_profile('brin_0', maps)['digest'] != (
        profiles.resolve_profile('banyak_simpangan', maps)['digest'])


def test_laptop_runs_only_rmf_core_and_profile_announcement(monkeypatch):
    module = load('laptop', monkeypatch)
    for name in ('brin_0', 'banyak_simpangan'):
        actions = module.setup(context(name))
        assert [action.node_package for action in actions] == [
            'rmf_traffic_ros2', 'rmf_task_ros2', 'rmf_building_map_tools',
            'brin_husky_distributed']
        assert actions[-1].node_executable == 'profile_announcer'


def test_robot_requires_laptop_and_defers_adapter_until_preflight(monkeypatch):
    module = load('robot', monkeypatch)
    for name in ('brin_0', 'banyak_simpangan'):
        ctx = context(name, 'true')
        handler, bridge, preflight = module.setup(ctx)
        assert bridge.node_package == preflight.node_package == 'brin_husky_hardware'
        assert isinstance(handler.event_handler.handle(
            SimpleNamespace(returncode=1), ctx)[0], EmitEvent)
        started = handler.event_handler.handle(SimpleNamespace(returncode=0), ctx)
        assert len(started) == 1 and isinstance(started[0], Node)
        assert started[0].node_executable == 'fleet_adapter'
        assert started[0].node_package == 'brin_husky_hardware'
        ctx.launch_configurations['enable_dispatch'] = 'false'
        assert isinstance(handler.event_handler.handle(
            SimpleNamespace(returncode=0), ctx)[0], EmitEvent)
        ctx.launch_configurations['start_nav2'] = 'true'
        assert isinstance(module.setup(ctx)[0], IncludeLaunchDescription)


def test_missing_or_duplicate_laptop_core_fails():
    core = [(name, '/') for name in (
        'rmf_traffic_schedule_primary', 'rmf_task_dispatcher',
        'building_map_server')]
    assert rmf_core_errors(core) == []
    assert len(rmf_core_errors(core[1:])) == 1
    assert len(rmf_core_errors(core + core[:1])) == 1
