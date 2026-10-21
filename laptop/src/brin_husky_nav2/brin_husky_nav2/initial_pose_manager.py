"""Initialize each active AMCL from map-derived spawn metadata, once confirmed."""
import math
from pathlib import Path
import yaml
import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from geometry_msgs.msg import PoseWithCovarianceStamped
from lifecycle_msgs.srv import GetState
from lifecycle_msgs.msg import State
from rclpy.qos import qos_profile_sensor_data


class InitialPoseManager(Node):
    def __init__(self):
        super().__init__('initial_pose_manager')
        self.declare_parameter('spawns', '')
        self.spawns = yaml.safe_load(Path(self.get_parameter('spawns').value).read_text())
        self.declare_parameter('robots', sorted(self.spawns))
        self.robots = {}
        for name in self.get_parameter('robots').value:
            self.robots[name] = dict(
                publisher=self.create_publisher(PoseWithCovarianceStamped, f'/{name}/initialpose', 1),
                client=self.create_client(GetState, f'/{name}/amcl/get_state'),
                future=None, active=False, sent=False, confirmed=False)
            self.create_subscription(PoseWithCovarianceStamped, f'/{name}/amcl_pose',
                                     lambda msg, n=name: self.confirm(n, msg), qos_profile_sensor_data)
        self.create_timer(1.0, self.tick)

    def confirm(self, name, msg):
        state = self.robots[name]
        if state['sent'] and not state['confirmed']:
            state['confirmed'] = True
            self.get_logger().info(f'{name}: AMCL initialization confirmed')

    def tick(self):
        for name, state in self.robots.items():
            if state['confirmed']:
                continue
            future = state['future']
            if future is not None and future.done():
                try:
                    state['active'] = future.result().current_state.id == State.PRIMARY_STATE_ACTIVE
                except Exception as exc:
                    self.get_logger().warning(str(exc))
                state['future'] = None
            if not state['active']:
                if state['future'] is None and state['client'].service_is_ready():
                    state['future'] = state['client'].call_async(GetState.Request())
                continue
            if not state['publisher'].get_subscription_count():
                continue
            pose = self.spawns[name]
            msg = PoseWithCovarianceStamped()
            msg.header.frame_id = 'map'
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.pose.pose.position.x, msg.pose.pose.position.y = pose['x'], pose['y']
            msg.pose.pose.orientation.z = math.sin(pose['yaw']/2)
            msg.pose.pose.orientation.w = math.cos(pose['yaw']/2)
            msg.pose.covariance[0] = msg.pose.covariance[7] = 0.04
            msg.pose.covariance[35] = 0.04
            state['publisher'].publish(msg)
            state['sent'] = True


def main(args=None):
    rclpy.init(args=args)
    node = InitialPoseManager()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
