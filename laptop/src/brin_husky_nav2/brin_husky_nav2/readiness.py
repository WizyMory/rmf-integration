"""Wait for active lifecycle nodes, fresh localization and independent actions."""
import time
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.time import Time
from lifecycle_msgs.srv import GetState
from nav2_msgs.action import NavigateToPose
from tf2_ros import Buffer, TransformListener, TransformException

NODES = ('amcl', 'controller_server', 'planner_server', 'smoother_server',
         'behavior_server', 'bt_navigator', 'waypoint_follower', 'velocity_smoother')


def main(args=None):
    rclpy.init(args=args)
    node = Node('nav2_readiness')
    node.declare_parameter('robot_names', '')
    node.declare_parameter('timeout', 180.0)
    names = [n for n in node.get_parameter('robot_names').value.split(',') if n]
    clients = {(r, n): node.create_client(GetState, f'/{r}/{n}/get_state')
               for r in names for n in NODES}
    actions = {r: ActionClient(node, NavigateToPose, f'/{r}/navigate_to_pose') for r in names}
    buffer = Buffer()
    listener = TransformListener(buffer, node)
    pending, active = {}, set()
    next_poll = {}
    deadline = time.monotonic()+node.get_parameter('timeout').value
    success = False
    try:
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            for key, client in clients.items():
                if key in active:
                    continue
                if key in pending:
                    future, sent = pending[key]
                    if future.done():
                        if future.result().current_state.id == 3:
                            active.add(key)
                        del pending[key]
                    elif time.monotonic()-sent > 5:
                        client.remove_pending_request(future)
                        del pending[key]
                elif time.monotonic() >= next_poll.get(key, 0) and client.service_is_ready():
                    next_poll[key] = time.monotonic()+0.5
                    pending[key] = (client.call_async(GetState.Request()), time.monotonic())
            if len(active) != len(clients):
                continue
            ready = True
            for robot in names:
                try:
                    tf = buffer.lookup_transform('map', robot+'/base_link', Time())
                    age = (node.get_clock().now()-Time.from_msg(tf.header.stamp)).nanoseconds/1e9
                    ready = ready and -0.5 <= age <= 2.0 and actions[robot].server_is_ready()
                except TransformException:
                    ready = False
            if ready:
                node.get_logger().info(f'Navigation ready: {names}; all lifecycle nodes active, fresh TF, action servers ready')
                success = True
                break
        if not success:
            node.get_logger().error(f'Navigation readiness timeout; inactive: {sorted(set(clients)-active)}')
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    raise SystemExit(0 if success else 1)
