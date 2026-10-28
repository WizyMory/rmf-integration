"""Check graph geometry, RViz compatibility, and visualization isolation."""
import importlib.util
from pathlib import Path

from launch import LaunchContext
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.utilities import evaluate_parameters
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
MAPS = ROOT.parent / 'brin_rmf_maps'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GRAPH = load_module('husky_rmf_graph', ROOT / 'scripts/rmf_graph_markers.py')
RVIZ = load_module('husky_rmf_rviz', ROOT / 'launch/rviz.launch.py')


@pytest.fixture(autouse=True)
def ros_log_directory(monkeypatch, tmp_path):
    monkeypatch.setenv('ROS_LOG_DIR', str(tmp_path / 'ros_logs'))


@pytest.mark.parametrize('profile', ['banyak_simpangan', 'brin_0'])
def test_overlay_uses_exported_metre_coordinates_for_each_profile(profile):
    profiles = yaml.safe_load((MAPS / 'maps/traffic_profiles.yaml').read_text())
    graph = yaml.safe_load((MAPS / 'nav_graphs' /
                           profiles['profiles'][profile]['nav_graph']).read_text())
    level = graph['levels']['L1']
    expected = {tuple(sorted((tuple(level['vertices'][lane[0]][:2]),
                              tuple(level['vertices'][lane[1]][:2]))))
                for lane in level['lanes']}
    marker, = GRAPH.graph_markers(MAPS, profile).markers
    actual = {tuple(sorted(((start.x, start.y), (finish.x, finish.y))))
              for start, finish in zip(marker.points[::2], marker.points[1::2])}
    assert actual == expected
    assert len(marker.points) == len(expected) * 2
    assert marker.header.frame_id == 'map'
    assert all(point.z > 0.0 for point in marker.points)
    assert marker.header.stamp.sec == marker.lifetime.sec == 0


def test_invalid_profile_and_negative_lane_index_are_rejected(tmp_path):
    with pytest.raises(ValueError, match='Unknown traffic_profile'):
        GRAPH.graph_markers(MAPS, 'does_not_exist')
    (tmp_path / 'maps').mkdir()
    (tmp_path / 'nav_graphs').mkdir()
    (tmp_path / 'maps/traffic_profiles.yaml').write_text(
        'profiles: {invalid: {nav_graph: bad.yaml}}')
    (tmp_path / 'nav_graphs/bad.yaml').write_text(yaml.safe_dump({
        'levels': {'L1': {'vertices': [[1.0, 2.0], [3.0, 4.0]],
                          'lanes': [[-1, 1, {}]]}}}))
    with pytest.raises(ValueError, match='Invalid lane vertex indices'):
        GRAPH.graph_markers(tmp_path, 'invalid')


@pytest.mark.parametrize('enabled', ['true', 'false'])
def test_stock_rviz_keeps_husky_topics_and_optional_overlay(enabled):
    context = LaunchContext()
    context.launch_configurations['show_rmf_graph'] = enabled
    stock = (Path(RVIZ.get_package_share_directory('nav2_bringup')) /
             'rviz/nav2_namespaced_view.rviz')
    output = Path(RVIZ.ConfigureRviz(
        str(stock), LaunchConfiguration('show_rmf_graph')).perform(context))
    try:
        config = yaml.safe_load(output.read_text())
        manager = config['Visualization Manager']
        assert manager['Global Options']['Fixed Frame'] == 'map'
        displays = {display['Name']: display for display in manager['Displays']}
        assert displays['RobotModel']['Enabled'] is True
        assert displays['RobotModel']['Description Topic']['Value'] == (
            '/a200_1060/robot_description')
        assert displays['LaserScan']['Color'] == '255; 255; 0'
        assert displays['LaserScan']['Color Transformer'] == 'FlatColor'
        assert displays['LaserScan']['Topic']['Value'] == '/a200_1060/scan'
        assert ('RMF navigation graph' in displays) is (enabled == 'true')
        if enabled == 'true':
            assert displays['RMF navigation graph']['Topic']['Durability Policy'] == (
                'Transient Local')
        assert displays['RMF scheduled traffic']['Topic']['Value'] == '/schedule_markers'
        assert displays['RMF fleet positions']['Topic']['Value'] == '/fleet_markers'
        assert '<robot_namespace>' not in output.read_text()
    finally:
        output.unlink()


def test_launch_starts_only_rviz_and_optional_graph_with_real_time():
    description = RVIZ.generate_launch_description()
    context = LaunchContext()
    for action in description.entities:
        if isinstance(action, DeclareLaunchArgument):
            action.execute(context)
    nodes = [action for action in description.entities if isinstance(action, Node)]
    assert {node._Node__node_executable for node in nodes} == {
        'rviz2', 'rmf_graph_markers.py'}
    for node in nodes:
        assert evaluate_parameters(context, node._Node__parameters)[0]['use_sim_time'] is False
    publisher = next(node for node in nodes
                     if node._Node__node_executable == 'rmf_graph_markers.py')
    assert evaluate_parameters(context, publisher._Node__parameters)[0][
        'traffic_profile'] == 'brin_0'
    assert publisher.condition.evaluate(context) is True
    context.launch_configurations['show_rmf_graph'] = 'false'
    assert publisher.condition.evaluate(context) is False
