"""The laptop owns RMF core; the robot only dispatches after strict preflight."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from launch import LaunchContext
from launch.actions import EmitEvent, IncludeLaunchDescription
from launch_ros.actions import Node
from launch_ros.utilities import evaluate_parameters
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
    if name in ('laptop', 'robot', 'visualization'):
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
        'rviz': 'false',
        'rviz_config': str(ROOT / 'brin_husky_distributed/rviz/husky_rmf.rviz'),
        'start_visualizers': 'true',
        'start_tf': 'true',
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
    assert profiles.resolve_profile('gedungWS_0', maps)['fleet_config'].name == (
        'gedungWS_0_fleet.yaml')
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


def test_rviz_option_keeps_one_core_and_adds_only_observation(monkeypatch):
    ctx = context()
    ctx.launch_configurations['rviz'] = 'true'
    laptop = load('laptop', monkeypatch)
    actions = laptop.setup(ctx)
    assert len(actions) == 5
    assert sum(isinstance(action, Node) and action.node_executable ==
               'rmf_traffic_schedule' for action in actions) == 1
    include = actions[-1]
    assert isinstance(include, IncludeLaunchDescription)
    monkeypatch.setattr('ament_index_python.packages.get_package_share_directory',
                        lambda package: str(ROOT / package))
    included = include.launch_description_source.get_launch_description(ctx)
    assert include.launch_description_source.location.endswith('/launch/visualization.launch.py')
    opaque, = [action for action in included.entities
               if type(action).__name__ == 'OpaqueFunction']
    nodes = opaque.execute(ctx)
    assert {node.node_package for node in nodes} == {
        'rviz2', 'rmf_visualization_navgraphs',
        'rmf_visualization_fleet_states', 'rmf_visualization_schedule', 'brin_husky_distributed'}
    fleet = yaml.safe_load((ROOT / 'brin_husky_distributed/config/fleet_config.yaml').read_text())
    for node in nodes:
        params = evaluate_parameters(ctx, node._Node__parameters)[0]
        assert params['use_sim_time'] is False
        if node.node_package not in ('rviz2', 'brin_husky_distributed'):
            assert params['initial_map_name'] == fleet['map_name']
        if node.node_package == 'rmf_visualization_fleet_states':
            assert params[fleet['fleet_name'] + '_radius'] == fleet['profile']['footprint']
            assert params['Devi_radius'] == 0.55
        if node.node_package == 'rviz2':
            assert node.condition.evaluate(ctx)
            ctx.launch_configurations['rviz'] = 'false'
            assert not node.condition.evaluate(ctx)
            remaps = {tuple(s.text for s in source): tuple(s.text for s in target)
                      for source, target in node._Node__remappings}
            assert remaps[('/tf',)] == ('/rmf_visualization/tf',)
            assert remaps[('/tf_static',)] == ('/rmf_visualization/tf_static',)


def test_gedung_default_rviz_accepts_manual_pose_for_devi_and_keeps_custom_presets(monkeypatch):
    module = load('laptop', monkeypatch)
    ctx = context('gedungWS_0')
    ctx.launch_configurations.update(rviz='true', rviz_config='')
    include = module.setup(ctx)[-1]
    arguments = dict(include.launch_arguments)
    assert arguments['rviz_config'].endswith('/rviz/devi_rmf.rviz')
    manager = yaml.safe_load(Path(arguments['rviz_config']).read_text())['Visualization Manager']
    pose_tools = [tool for tool in manager['Tools'] if tool['Class'].endswith('/SetInitialPose')]
    assert [tool['Topic']['Value'] for tool in pose_tools] == ['/devi/initialpose']
    displays = {display['Name']: display for display in manager['Displays']}
    assert displays['Shared gedungWS_0 map from Devi']['Topic']['Value'] == '/devi/map'
    assert displays['RMF fleet positions']['Topic']['Value'] == '/fleet_markers'
    ctx.launch_configurations['rviz_config'] = '/custom/operator.rviz'
    assert dict(module.setup(ctx)[-1].launch_arguments)['rviz_config'] == '/custom/operator.rviz'


def test_physical_rviz_loads_latched_graph_and_live_fleet_markers():
    config = yaml.safe_load((ROOT / 'brin_husky_distributed/rviz/husky_rmf.rviz').read_text())
    manager = config['Visualization Manager']
    assert manager['Global Options']['Fixed Frame'] == 'map'
    # RViz may save additional displays for the same topic. Check the named
    # preset layers so an operator's extra panels do not hide their settings.
    displays = {display['Name']: display for display in manager['Displays']}
    for name, topic, durability in [
            ('RMF lanes and waypoints', '/map_markers', 'Transient Local'),
            ('RMF fleet positions', '/fleet_markers', 'Volatile'),
            ('RMF scheduled traffic', '/schedule_markers', 'Volatile')]:
        display = displays[name]
        assert display['Enabled']
        assert display['Class'] == 'rviz_default_plugins/MarkerArray'
        assert display['Topic']['Value'] == topic
        assert display['Topic']['Durability Policy'] == durability
    assert displays['Husky Nav2 map']['Topic']['Durability Policy'] == 'Transient Local'
    assert displays['Husky Hokuyo']['Topic']['Reliability Policy'] == 'Best Effort'


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
