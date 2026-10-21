import importlib.util
from pathlib import Path

from launch import LaunchContext
from launch.actions import DeclareLaunchArgument
from launch_ros.actions import Node
from launch_ros.utilities import evaluate_parameters
import pytest
import yaml

from brin_husky_bringup.documentation_markers import (
    MESH_RESOURCE, graph_markers, obstacle_markers)


ROOT = Path(__file__).resolve().parents[2]
MAPS = ROOT/'brin_rmf_maps'


def test_obstacle_markers_match_main_world_and_use_local_mesh():
    markers = obstacle_markers(MAPS).markers
    meshes = [marker for marker in markers if marker.ns == 'unregistered_obstacles']
    labels = [marker for marker in markers
              if marker.ns == 'unregistered_obstacle_labels']
    assert len(meshes) == len(labels) == 2
    assert [marker.pose.position.x for marker in meshes] == pytest.approx(
        [88.91224640325312, 80.62981859999542])
    assert [marker.pose.position.y for marker in meshes] == pytest.approx(
        [-12.39592128107989, -10.131197244838491])
    assert all(marker.mesh_resource == MESH_RESOURCE for marker in meshes)
    assert all(marker.mesh_use_embedded_materials for marker in meshes)
    assert all(marker.scale.x == marker.scale.y == marker.scale.z == 0.01
               for marker in meshes)
    assert all('UNREGISTERED OBSTACLE' in marker.text for marker in labels)


def test_graph_markers_follow_selected_profile_without_duplicate_edges():
    graph = graph_markers(MAPS, 'banyak_simpangan').markers[0]
    source = yaml.safe_load(
        (MAPS/'nav_graphs/banyak_simpangan.yaml').read_text())['levels']['L1']
    unique_edges = {tuple(sorted((int(lane[0]), int(lane[1]))))
                    for lane in source['lanes']}
    assert len(graph.points) == 2*len(unique_edges)
    assert graph.header.frame_id == 'map'
    assert graph.scale.x == pytest.approx(0.08)


def test_documentation_launch_has_no_gazebo_or_robot_processes(monkeypatch, tmp_path):
    monkeypatch.setenv('ROS_LOG_DIR', str(tmp_path))
    path = ROOT/'brin_husky_bringup/launch/rviz_documentation.launch.py'
    spec = importlib.util.spec_from_file_location('rviz_documentation_launch', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    context = LaunchContext()
    for action in module.generate_launch_description().entities:
        if isinstance(action, DeclareLaunchArgument):
            action.execute(context)
    context.launch_configurations['rviz'] = 'false'
    actions = module.launch_setup(context)
    nodes = {action._Node__node_executable: action for action in actions
             if isinstance(action, Node)}
    assert set(nodes) == {
        'map_server', 'lifecycle_manager', 'publish_documentation_markers', 'rviz2'}
    assert not {'ign gazebo', 'parameter_bridge', 'fleet_adapter'} & set(nodes)
    parameters = evaluate_parameters(
        context, nodes['publish_documentation_markers']._Node__parameters)[0]
    assert parameters == {'use_sim_time': True,
                          'traffic_profile': 'banyak_simpangan'}


def test_documentation_rviz_shows_map_graph_and_obstacles():
    config = yaml.safe_load(
        (ROOT/'brin_husky_bringup/rviz/brin_obstacles.rviz').read_text())
    displays = config['Visualization Manager']['Displays']
    topics = {display['Name']: display['Topic'] for display in displays}
    assert topics['BRIN occupancy']['Value'] == '/map'
    assert topics['RMF navigation graph']['Value'] == '/rmf_graph_markers'
    assert topics['Unregistered CGM obstacles']['Value'] == '/obstacle_markers'
    assert all(topic['Durability Policy'] == 'Transient Local'
               for topic in topics.values())
