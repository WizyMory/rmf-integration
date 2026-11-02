"""Read-only RMF domain-0 observer with an independently owned context."""
import rclpy
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node


class RmfObserver:
    def __init__(self):
        self.context = Context()
        rclpy.init(args=[], context=self.context, domain_id=0)
        self.node = Node('devi_rmf_observer', context=self.context,
                         use_global_arguments=False)
        self.executor = SingleThreadedExecutor(context=self.context)
        self.executor.add_node(self.node)

    def spin_once(self):
        self.executor.spin_once(timeout_sec=0.0)

    def close(self):
        self.executor.shutdown(timeout_sec=2.0)
        self.node.destroy_node()
        self.context.try_shutdown()
