"""Exercise staged launch expansion, subset selection and child costmap parameters."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
import yaml
from launch import LaunchContext
from launch.actions import DeclareLaunchArgument, RegisterEventHandler, EmitEvent
from launch_ros.actions import ComposableNodeContainer, Node
from launch_ros.utilities import evaluate_parameters


@pytest.mark.parametrize('batch_size', [1, 2, 3])
@pytest.mark.parametrize('enabled', [('husky_0', 'husky_6'), tuple(f'husky_{i}' for i in range(7))])
def test_staged_composition_and_subset(batch_size, enabled, monkeypatch, tmp_path):
    monkeypatch.setenv('ROS_LOG_DIR', str(tmp_path))
    path = Path(__file__).resolve().parents[1]/'launch/navigation.launch.py'
    spec = importlib.util.spec_from_file_location('navigation_launch', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    context = LaunchContext()
    for action in module.generate_launch_description().entities:
        if isinstance(action, DeclareLaunchArgument):
            action.execute(context)
    for name in module.robot_names():
        context.launch_configurations['start_'+name] = str(name in enabled).lower()
    context.launch_configurations['nav2_start_batch_size'] = str(batch_size)
    actions = module.launch_setup(context)
    map_server = next(a for a in actions if isinstance(a, Node)
                      and a._Node__node_executable == 'map_server')
    map_parameters = evaluate_parameters(context, map_server._Node__parameters)
    expected_map = ('banyak_simpangan.yaml'
                    if context.launch_configurations.get('traffic_profile') == 'banyak_simpangan'
                    else 'brin_0.yaml')
    assert Path(map_parameters[0]['yaml_filename']).name == expected_map
    handlers = [a for a in actions if isinstance(a, RegisterEventHandler)]
    containers = [a for a in actions if isinstance(a, ComposableNodeContainer)]
    assert len(handlers) == (len(enabled)+batch_size-1)//batch_size
    assert len(containers) == min(batch_size, len(enabled))
    for index, handler in enumerate(handlers):
        following = handler.event_handler.handle(SimpleNamespace(returncode=0), context)
        containers += [a for a in following if isinstance(a, ComposableNodeContainer)]
        failed = handler.event_handler.handle(SimpleNamespace(returncode=1), context)
        assert len(failed) == 1 and isinstance(failed[0], EmitEvent)
        assert bool(following) == (index+1 < len(handlers))
    assert len(containers) == len(enabled)
    for name, container in zip(enabled, containers):
        # The process itself needs the whole YAML: child costmaps are not loaded
        # through the component service and otherwise silently use default frames.
        params = evaluate_parameters(context, container._Node__parameters)
        tree = yaml.safe_load(Path(params[0]).read_text())
        assert set(tree) == {name}
        local = tree[name]['local_costmap']['local_costmap']['ros__parameters']
        assert local['robot_base_frame'] == name+'/base_link'
        assert local['global_frame'] == name+'/odom'


def test_banyak_simpangan_selects_its_nav2_map(monkeypatch, tmp_path):
    monkeypatch.setenv('ROS_LOG_DIR', str(tmp_path))
    path = Path(__file__).resolve().parents[1]/'launch/navigation.launch.py'
    spec = importlib.util.spec_from_file_location('navigation_launch_profile', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    context = LaunchContext()
    for action in module.generate_launch_description().entities:
        if isinstance(action, DeclareLaunchArgument):
            action.execute(context)
    context.launch_configurations['traffic_profile'] = 'banyak_simpangan'
    for name in module.robot_names():
        context.launch_configurations['start_'+name] = 'false'
    actions = module.launch_setup(context)
    map_server = next(a for a in actions if isinstance(a, Node)
                      and a._Node__node_executable == 'map_server')
    params = evaluate_parameters(context, map_server._Node__parameters)
    assert Path(params[0]['yaml_filename']).name == 'banyak_simpangan.yaml'
