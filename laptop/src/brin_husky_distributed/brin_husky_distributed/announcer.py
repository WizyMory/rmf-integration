"""Publish the selected laptop map/graph identity for robot preflight."""

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


class ProfileAnnouncer(Node):
    def __init__(self):
        super().__init__('brin_hardware_profile_announcer')
        self.declare_parameter('profile_digest', '')
        digest = self.get_parameter('profile_digest').value
        if len(digest) != 64:
            raise ValueError('profile_digest must be a SHA-256 hex digest')
        self.message = String(data=digest)
        self.publisher = self.create_publisher(
            String, '/brin_hardware/profile_digest',
            QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.timer = self.create_timer(1.0, self.publish)
        self.publish()

    def publish(self):
        self.publisher.publish(self.message)


def main(args=None):
    rclpy.init(args=args)
    node = ProfileAnnouncer()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
