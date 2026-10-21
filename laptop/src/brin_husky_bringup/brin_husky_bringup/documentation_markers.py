"""Publish the RMF graph and simulation-only obstacles for RViz documentation."""
from pathlib import Path
import math
import xml.etree.ElementTree as ET

from ament_index_python.packages import get_package_share_directory as share
from geometry_msgs.msg import Point
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from visualization_msgs.msg import Marker, MarkerArray
import yaml


MESH_RESOURCE = (
    'package://brin_rmf_maps/models/CGMClassic/meshes/CGMClassic.obj')


def _pose(marker, values):
    x, y, z, roll, pitch, yaw = values
    marker.pose.position.x = x
    marker.pose.position.y = y
    marker.pose.position.z = z
    # The generated props only use yaw. Keep the conversion explicit so the
    # RViz pose is identical to the main Gazebo world.
    marker.pose.orientation.z = math.sin(yaw / 2.0)
    marker.pose.orientation.w = math.cos(yaw / 2.0)
    if abs(roll) > 1e-9 or abs(pitch) > 1e-9:
        raise ValueError('Documentation obstacle unexpectedly uses roll or pitch')


def obstacle_markers(maps):
    """Build transient RViz markers from the generated main-world includes."""
    maps = Path(maps)
    world = ET.parse(maps/'worlds/brin.sdf').getroot().find('world')
    includes = [include for include in world.findall('include')
                if include.findtext('uri') == 'model://CGMClassic']
    result = MarkerArray()
    for index, include in enumerate(includes):
        name = include.findtext('name')
        values = [float(value) for value in include.findtext('pose').split()]
        mesh = Marker()
        mesh.header.frame_id = 'map'
        mesh.ns = 'unregistered_obstacles'
        mesh.id = index
        mesh.type = Marker.MESH_RESOURCE
        mesh.action = Marker.ADD
        _pose(mesh, values)
        mesh.scale.x = mesh.scale.y = mesh.scale.z = 0.01
        mesh.color.r = mesh.color.g = mesh.color.b = mesh.color.a = 1.0
        mesh.mesh_resource = MESH_RESOURCE
        mesh.mesh_use_embedded_materials = True
        result.markers.append(mesh)

        label = Marker()
        label.header.frame_id = 'map'
        label.ns = 'unregistered_obstacle_labels'
        label.id = index
        label.type = Marker.TEXT_VIEW_FACING
        label.action = Marker.ADD
        label.pose.position.x = values[0]
        label.pose.position.y = values[1]
        label.pose.position.z = 1.4
        label.pose.orientation.w = 1.0
        label.scale.z = 0.55
        label.color.r = 1.0
        label.color.g = 0.25
        label.color.b = 0.05
        label.color.a = 1.0
        label.text = f'{name}\nUNREGISTERED OBSTACLE'
        result.markers.append(label)
    if not includes:
        raise ValueError('Main world contains no CGMClassic obstacle includes')
    return result


def graph_markers(maps, profile_name):
    """Build a de-duplicated line list for the selected RMF traffic graph."""
    maps = Path(maps)
    profiles = yaml.safe_load((maps/'maps/traffic_profiles.yaml').read_text())
    if profile_name not in profiles['profiles']:
        available = ', '.join(sorted(profiles['profiles']))
        raise ValueError(
            f'Unknown traffic profile [{profile_name}]. Available: {available}')
    graph_path = maps/'nav_graphs'/profiles['profiles'][profile_name]['nav_graph']
    level = yaml.safe_load(graph_path.read_text())['levels']['L1']
    marker = Marker()
    marker.header.frame_id = 'map'
    marker.ns = 'rmf_navigation_graph'
    marker.id = 0
    marker.type = Marker.LINE_LIST
    marker.action = Marker.ADD
    marker.pose.orientation.w = 1.0
    marker.scale.x = 0.08
    marker.color.r = 0.0
    marker.color.g = 0.75
    marker.color.b = 1.0
    marker.color.a = 0.70
    seen = set()
    for lane in level['lanes']:
        start, finish = int(lane[0]), int(lane[1])
        edge = tuple(sorted((start, finish)))
        if edge in seen:
            continue
        seen.add(edge)
        for vertex_index in (start, finish):
            vertex = level['vertices'][vertex_index]
            marker.points.append(Point(x=float(vertex[0]), y=float(vertex[1]), z=0.08))
    return MarkerArray(markers=[marker])


class DocumentationMarkers(Node):
    def __init__(self):
        super().__init__('brin_documentation_markers')
        self.declare_parameter('traffic_profile', 'banyak_simpangan')
        profile = self.get_parameter('traffic_profile').value
        maps = Path(share('brin_rmf_maps'))
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.obstacle_publisher = self.create_publisher(
            MarkerArray, '/obstacle_markers', qos)
        self.graph_publisher = self.create_publisher(
            MarkerArray, '/rmf_graph_markers', qos)
        obstacles = obstacle_markers(maps)
        graph = graph_markers(maps, profile)
        self.obstacle_publisher.publish(obstacles)
        self.graph_publisher.publish(graph)
        self.get_logger().info(
            f'Published {len(obstacles.markers)//2} CGMClassic obstacles and '
            f'{len(graph.markers[0].points)//2} RMF graph lanes for [{profile}]')


def main(args=None):
    rclpy.init(args=args)
    node = DocumentationMarkers()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
