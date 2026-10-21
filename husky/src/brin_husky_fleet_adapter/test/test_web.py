"""Regression coverage for optional Web telemetry and launch propagation."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest
from launch import LaunchContext
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.utilities import perform_substitutions
from launch_ros.utilities import evaluate_parameters

from brin_husky_fleet_adapter.web import add_fleet

ROOT = Path(__file__).resolve().parents[2]


def load_launch(package, filename):
    spec = importlib.util.spec_from_file_location(filename, ROOT/package/'launch'/filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('uri', ['', 'ws://localhost:8000/_internal'])
def test_add_fleet_optional_uri(uri):
    native = Mock()
    traits, graph = object(), object()
    result = add_fleet(native, 'HuskyA200', traits, graph, uri)
    args = ('HuskyA200', traits, graph) + ((uri,) if uri else ())
    native.add_fleet.assert_called_once_with(*args)
    assert result is native.add_fleet.return_value


@pytest.mark.parametrize('uri', ['', 'ws://localhost:8000/_internal'])
def test_launch_defaults_and_propagation(uri, monkeypatch, tmp_path):
    monkeypatch.setenv('ROS_LOG_DIR', str(tmp_path))
    full = load_launch('brin_husky_bringup', 'full_system.launch.py')
    rmf = load_launch('brin_husky_fleet_adapter', 'rmf.launch.py')
    context = LaunchContext()
    full_description = full.generate_launch_description()
    for description in (full_description, rmf.generate_launch_description()):
        declarations = [e for e in description.entities if isinstance(e, DeclareLaunchArgument)]
        server = next(e for e in declarations if e.name == 'server_uri')
        assert perform_substitutions(context, server.default_value) == ''
        for declaration in declarations:
            declaration.execute(context)
    context.launch_configurations['server_uri'] = uri
    from types import SimpleNamespace
    staged = next(e for e in full_description.entities if isinstance(e, OpaqueFunction)).execute(context)
    handler, simulation, gate = staged
    following = handler.event_handler.handle(SimpleNamespace(returncode=0), context)
    nav_handler, navigation, nav_gate = following
    after_navigation = nav_handler.event_handler.handle(SimpleNamespace(returncode=0), context)
    includes = [e for e in [simulation, navigation, *after_navigation] if isinstance(e, IncludeLaunchDescription)]
    assert all('server_uri' not in dict(e.launch_arguments) for e in includes[:2])
    forwarded = dict(includes[2].launch_arguments)['server_uri'].perform(context)
    assert forwarded == uri
    assert dict(includes[2].launch_arguments)['traffic_profile'].perform(context) == ''
    nodes = rmf.launch_setup(context)
    params = evaluate_parameters(context, nodes[-1]._Node__parameters)
    assert params[0]['server_uri'] == uri
    assert tuple(params[0]['robots']) == tuple(f'husky_{i}' for i in range(7))
    assert Path(nodes[2]._Node__arguments[0]).name == 'brin_0.building.yaml'
    assert Path(params[0]['nav_graph']).name == 'simulation.yaml'


def test_unknown_traffic_profile_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv('ROS_LOG_DIR', str(tmp_path))
    rmf = load_launch('brin_husky_fleet_adapter', 'rmf.launch.py')
    context = LaunchContext()
    for declaration in rmf.generate_launch_description().entities:
        if isinstance(declaration, DeclareLaunchArgument):
            declaration.execute(context)
    context.launch_configurations['traffic_profile'] = 'does_not_exist'
    with pytest.raises(ValueError, match='Unknown traffic_profile'):
        rmf.launch_setup(context)


def test_banyak_simpangan_profile_selects_matching_files(monkeypatch, tmp_path):
    monkeypatch.setenv('ROS_LOG_DIR', str(tmp_path))
    rmf = load_launch('brin_husky_fleet_adapter', 'rmf.launch.py')
    context = LaunchContext()
    for declaration in rmf.generate_launch_description().entities:
        if isinstance(declaration, DeclareLaunchArgument):
            declaration.execute(context)
    context.launch_configurations['traffic_profile'] = 'banyak_simpangan'
    nodes = rmf.launch_setup(context)
    params = evaluate_parameters(context, nodes[-1]._Node__parameters)
    assert Path(nodes[2]._Node__arguments[0]).name == 'banyak_simpangan.building.yaml'
    assert Path(params[0]['nav_graph']).name == 'banyak_simpangan.yaml'


def test_cli_entrypoint_and_fleet_identity_remain_available():
    import yaml
    config = yaml.safe_load((ROOT/'brin_husky_fleet_adapter/config/fleet_config.yaml').read_text())
    assert config['fleet_name'] == 'HuskyA200'
    assert set(config['robots']) == {f'husky_{i}' for i in range(7)}
    assert config['max_merge_lane_distance'] == 1.0
    from brin_husky_fleet_adapter.send_task import main
    assert callable(main)
    assert 'send_task = brin_husky_fleet_adapter.send_task:main' in (
        ROOT/'brin_husky_fleet_adapter/setup.py').read_text()


def test_full_system_gates_only_enabled_robots(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from launch.actions import EmitEvent
    monkeypatch.setenv('ROS_LOG_DIR', str(tmp_path))
    module = load_launch('brin_husky_bringup', 'full_system.launch.py')
    context = LaunchContext()
    description = module.generate_launch_description()
    for action in description.entities:
        if isinstance(action, DeclareLaunchArgument):
            action.execute(context)
    enabled = ['husky_1', 'husky_6']
    for name in module.robot_names():
        context.launch_configurations['start_'+name] = str(name in enabled).lower()
    handler, simulation, gate = next(e for e in description.entities if isinstance(e, OpaqueFunction)).execute(context)
    assert evaluate_parameters(context, gate._Node__parameters)[0]['robot_names'] == ','.join(enabled)
    failed = handler.event_handler.handle(SimpleNamespace(returncode=1), context)
    assert isinstance(failed[0], EmitEvent)
    nav_handler, navigation, nav_gate = handler.event_handler.handle(SimpleNamespace(returncode=0), context)
    assert evaluate_parameters(context, nav_gate._Node__parameters)[0]['robot_names'] == ','.join(enabled)
    assert isinstance(nav_handler.event_handler.handle(SimpleNamespace(returncode=1), context)[0], EmitEvent)
