"""Check that the RMF launch and every RViz profile expose both marker layers."""
import importlib.util
from pathlib import Path

import pytest
import yaml
from launch import LaunchContext
from launch.actions import DeclareLaunchArgument
from launch_ros.actions import Node
from launch_ros.utilities import evaluate_parameters


ROOT = Path(__file__).resolve().parents[2]


def load_rmf_launch():
    path = ROOT/'brin_husky_fleet_adapter/launch/rmf.launch.py'
    spec = importlib.util.spec_from_file_location('rmf_visualization_launch', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('enabled', ['true', 'false'])
def test_rmf_visualizers_follow_launch_argument(enabled, monkeypatch, tmp_path):
    monkeypatch.setenv('ROS_LOG_DIR', str(tmp_path))
    module = load_rmf_launch()
    context = LaunchContext()
    for action in module.generate_launch_description().entities:
        if isinstance(action, DeclareLaunchArgument):
            action.execute(context)
    context.launch_configurations['rmf_visualization'] = enabled
    for name in module.robot_names():
        context.launch_configurations['start_'+name] = 'false'

    actions = module.launch_setup(context)
    nodes = {action._Node__node_executable: action for action in actions
             if isinstance(action, Node)}
    expected = {
        'schedule_visualizer_node': 'rmf_visualization_schedule',
        'fleetstates_visualizer_node': 'rmf_visualization_fleet_states'}
    for executable, package in expected.items():
        node = nodes[executable]
        assert node._Node__package == package
        assert node.condition.evaluate(context) is (enabled == 'true')
        parameters = evaluate_parameters(context, node._Node__parameters)[0]
        assert parameters['use_sim_time'] is True
        assert parameters['initial_map_name'] == 'L1'
    assert nodes['schedule_visualizer_node'].output[0].text == 'log'
    assert evaluate_parameters(
        context, nodes['fleetstates_visualizer_node']._Node__parameters
    )[0]['HuskyA200_radius'] == pytest.approx(0.55)


@pytest.mark.parametrize('profile', ['brin.rviz', 'brin_light.rviz', 'brin_debug.rviz'])
def test_rviz_profiles_show_rmf_schedule_and_fleet_markers(profile):
    path = ROOT/'brin_husky_nav2/rviz'/profile
    config = yaml.safe_load(path.read_text())
    displays = config['Visualization Manager']['Displays']
    markers = {display['Name']: display for display in displays
               if display['Class'] == 'rviz_default_plugins/MarkerArray'}
    assert markers['RMF scheduled traffic']['Topic']['Value'] == '/schedule_markers'
    assert markers['RMF fleet positions']['Topic']['Value'] == '/fleet_markers'
    assert all(marker['Enabled'] for marker in markers.values())
    assert all(marker['Topic']['Reliability Policy'] == 'Reliable'
               for marker in markers.values())
    assert all(marker['Topic']['Durability Policy'] == 'Volatile'
               for marker in markers.values())
