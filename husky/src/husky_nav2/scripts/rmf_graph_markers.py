#!/usr/bin/env python3
"""Display RMF graph lanes without starting navigation or sending robot goals."""

import math
from pathlib import Path

from ament_index_python.packages import (
    PackageNotFoundError, get_package_share_directory,
)
from geometry_msgs.msg import Point
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from visualization_msgs.msg import Marker, MarkerArray
import yaml


def graph_markers(maps, profile_name):
    """Use the exported graph's metre coordinates directly in Nav2's map frame.

    Reverse lanes share one visible segment. This overlay shows geometry,
    not lane direction, closures, or traffic reservations.
    """
    maps = Path(maps)
    profiles = yaml.safe_load((maps / 'maps/traffic_profiles.yaml').read_text())['profiles']
    if profile_name not in profiles:
        raise ValueError(f'Unknown traffic_profile [{profile_name}]; available: '
                         + ', '.join(sorted(profiles)))
    graph = yaml.safe_load(
        (maps / 'nav_graphs' / profiles[profile_name]['nav_graph']).read_text())
    level = graph['levels']['L1']
    vertices = level['vertices']
    marker = Marker()
    marker.header.frame_id = 'map'
    marker.ns = 'rmf_navigation_graph'
    marker.id = 0
    marker.type = Marker.LINE_LIST
    marker.action = Marker.ADD
    marker.pose.orientation.w = 1.0
    marker.scale.x = 0.08
    marker.color.g = 0.75
    marker.color.b = 1.0
    marker.color.a = 0.85
    edges = set()
    for lane in level['lanes']:
        start, finish = lane[:2]
        if any(type(index) is not int or not 0 <= index < len(vertices)
               for index in (start, finish)):
            raise ValueError(f'Invalid lane vertex indices: {lane}')
        edge = tuple(sorted((start, finish)))
        if edge in edges:
            continue
        edges.add(edge)
        for index in (start, finish):
            x, y = map(float, vertices[index][:2])
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError(f'Non-finite graph coordinates at vertex {index}')
            marker.points.append(Point(x=x, y=y, z=0.08))
    return MarkerArray(markers=[marker])


class RmfGraphMarkers(Node):
    def __init__(self):
        super().__init__('rmf_graph_markers')
        self.declare_parameter('traffic_profile', 'brin_0')
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.publisher = self.create_publisher(
            MarkerArray, 'rviz/rmf_graph_markers', qos)

    def publish_graph(self):
        profile = self.get_parameter('traffic_profile').value
        maps = get_package_share_directory('brin_rmf_maps')
        markers = graph_markers(maps, profile)
        # Zero timestamp and infinite lifetime keep this static overlay visible
        # for RViz subscribers that connect after the single cached publication.
        self.publisher.publish(markers)
        self.get_logger().info(
            f'RMF graph [{profile}]: {len(markers.markers[0].points) // 2} '
            'segments in map frame (visualization only)')


def main(args=None):
    rclpy.init(args=args)
    node = RmfGraphMarkers()
    try:
        node.publish_graph()
        rclpy.spin(node)
    except (PackageNotFoundError, OSError, ValueError, KeyError, TypeError,
            yaml.YAMLError) as error:
        node.get_logger().error(
            f'RMF graph overlay unavailable: {error}. Nav2 and RViz remain independent.')
        return 1
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
