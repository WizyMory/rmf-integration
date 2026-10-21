#!/usr/bin/env python3
"""Relay only the Husky wheel transforms into Nav2's private TF tree.

Clearpath publishes the wheel joints on /a200_1060/tf together with its own
odom -> base_link transform.  Nav2 uses /a200_1060/nav/tf so that its separate
EKF can own odom -> base_link.  Relaying only the four wheels makes the robot
model complete without creating a second odom -> base_link authority.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from tf2_msgs.msg import TFMessage


WHEEL_FRAMES = frozenset({
    'front_left_wheel',
    'front_right_wheel',
    'rear_left_wheel',
    'rear_right_wheel',
})


class WheelTfRelay(Node):
    def __init__(self):
        super().__init__('wheel_tf_relay')
        tf_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=100,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        self._publisher = self.create_publisher(
            TFMessage, '/a200_1060/nav/tf', tf_qos)
        self._subscription = self.create_subscription(
            TFMessage, '/a200_1060/tf', self._relay_wheels, tf_qos)
        self._seen_frames = set()
        self.get_logger().info(
            'Relaying wheel transforms from /a200_1060/tf to '
            '/a200_1060/nav/tf')

    def _relay_wheels(self, message):
        selected = [
            transform for transform in message.transforms
            if transform.child_frame_id.lstrip('/') in WHEEL_FRAMES
        ]
        if not selected:
            return

        self._publisher.publish(TFMessage(transforms=selected))
        previous_count = len(self._seen_frames)
        self._seen_frames.update(
            transform.child_frame_id.lstrip('/') for transform in selected)
        if previous_count < len(WHEEL_FRAMES) == len(self._seen_frames):
            self.get_logger().info('All four wheel transforms are available.')


def main(args=None):
    rclpy.init(args=args)
    node = WheelTfRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            node.destroy_node()
        except (Exception, KeyboardInterrupt):
            # ros2 launch may deliver another SIGINT while nodes are tearing
            # down; the ROS context is already on its way out in that case.
            pass
        if rclpy.ok():
            try:
                rclpy.shutdown()
            except (Exception, KeyboardInterrupt):
                pass


if __name__ == '__main__':
    main()
