"""Manual RViz initial pose and actual map across the two existing domains."""
import argparse
import math
import sys

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import OccupancyGrid

from .gateway import Nav2Gateway
from .profiles import load_settings


def validate_initial_pose(message):
    if message.header.frame_id != 'map':
        raise ValueError('Devi initial pose must be expressed in the shared map frame')
    position, rotation = message.pose.pose.position, message.pose.pose.orientation
    values = [position.x, position.y, position.z, rotation.x, rotation.y, rotation.z, rotation.w,
              *message.pose.covariance]
    if not all(math.isfinite(value) for value in values):
        raise ValueError('Initial pose contains a nonfinite value')
    norm = rotation.x**2 + rotation.y**2 + rotation.z**2 + rotation.w**2
    if abs(norm - 1.) > 0.01:
        raise ValueError('Initial pose quaternion must be normalized')


class InitialPoseBridge(Node):
    def __init__(self, settings):
        super().__init__('devi_initial_pose_bridge')
        self.gateway = Nav2Gateway(settings, allow_initial_pose=True, relay_map=True)
        self.subscription = self.create_subscription(PoseWithCovarianceStamped,
            '/devi/initialpose', self.initial_pose, 10)
        self.map_publisher = self.create_publisher(OccupancyGrid, '/devi/map',
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.last_map = None
        self.timer = self.create_timer(0.05, self.poll)
        self.get_logger().info('Manual pose correction available on /devi/initialpose')

    def initial_pose(self, message):
        try:
            validate_initial_pose(message)
            if not self.gateway.process.is_alive():
                raise RuntimeError('Nav2 gateway is not running')
            self.gateway.send({'op': 'initial_pose', 'pose': message})
            self.get_logger().info('Forwarded manual initial pose to Devi AMCL (domain 73)')
        except (ValueError, RuntimeError, OSError) as exc:
            self.get_logger().error(str(exc))

    def poll(self):
        self.gateway.poll()
        if not self.gateway.process.is_alive():
            raise RuntimeError('Devi Nav2 map/initial-pose gateway exited')
        if self.gateway.map_message is not None and self.gateway.map_message is not self.last_map:
            self.last_map = self.gateway.map_message
            self.map_publisher.publish(self.last_map)


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    argv = sys.argv if args is None else [sys.argv[0], *args]
    options = parser.parse_args(rclpy.utilities.remove_ros_args(argv)[1:])
    settings = load_settings(options.config)
    rclpy.init(args=argv, domain_id=0)
    node = None
    try:
        node = InitialPoseBridge(settings)
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.gateway.close()
            node.destroy_node()
        rclpy.try_shutdown()
