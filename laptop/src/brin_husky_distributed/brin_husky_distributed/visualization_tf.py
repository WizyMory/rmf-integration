"""Combine observed robot TF on topics used exclusively by RViz."""
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from tf2_msgs.msg import TFMessage


class VisualizationTF(Node):
    def __init__(self):
        super().__init__('rmf_visualization_tf')
        self.static = {}
        self.dynamic_publisher = self.create_publisher(TFMessage, '/rmf_visualization/tf', 100)
        self.static_publisher = self.create_publisher(TFMessage, '/rmf_visualization/tf_static',
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.keep = []
        for topic in ('/a200_1060/nav/tf', '/devi/viz/tf'):
            self.keep.append(self.create_subscription(TFMessage, topic, self.dynamic_publisher.publish,
                QoSProfile(depth=100, reliability=ReliabilityPolicy.BEST_EFFORT)))
        for topic in ('/a200_1060/tf_static', '/devi/viz/tf_static'):
            self.keep.append(self.create_subscription(TFMessage, topic, self.on_static,
                QoSProfile(depth=100, durability=DurabilityPolicy.TRANSIENT_LOCAL)))

    def on_static(self, message):
        self.static.update({item.child_frame_id: item for item in message.transforms})
        self.static_publisher.publish(TFMessage(transforms=list(self.static.values())))


def main(args=None):
    rclpy.init(args=args)
    node = VisualizationTF()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
