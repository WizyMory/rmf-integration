"""Gate navigation startup on active controllers, using wall-time deadlines."""
import time
import rclpy
from rclpy.node import Node
from controller_manager_msgs.srv import ListControllers


def controllers_ready(controllers):
    states = {c.name: c.state for c in controllers}
    return all(states.get(name) == 'active' for name in
               ('joint_state_broadcaster', 'platform_velocity_controller'))


def main(args=None):
    rclpy.init(args=args)
    node = Node('brin_controller_readiness')
    node.declare_parameter('robot_names', '')
    node.declare_parameter('timeout', 180.0)
    robots = node.get_parameter('robot_names').value.split(',')
    robots = [r for r in robots if r]
    clients = {r: node.create_client(ListControllers, f'/{r}/controller_manager/list_controllers')
               for r in robots}
    pending, ready = {}, set()
    next_poll = {}
    deadline = time.monotonic()+node.get_parameter('timeout').value
    try:
        while rclpy.ok() and time.monotonic() < deadline and len(ready) != len(robots):
            rclpy.spin_once(node, timeout_sec=0.1)
            for name, client in clients.items():
                if name in ready:
                    continue
                if name in pending:
                    future, sent = pending[name]
                    if future.done():
                        try:
                            if controllers_ready(future.result().controller):
                                ready.add(name)
                                node.get_logger().info(f'{name}: controllers active')
                        except Exception as exc:
                            node.get_logger().warning(str(exc))
                        del pending[name]
                    elif time.monotonic()-sent > 5.0:
                        client.remove_pending_request(future)
                        del pending[name]
                elif time.monotonic() >= next_poll.get(name, 0) and client.service_is_ready():
                    next_poll[name] = time.monotonic()+0.5
                    pending[name] = (client.call_async(ListControllers.Request()), time.monotonic())
        success = len(ready) == len(robots)
        if not success:
            node.get_logger().error(f'Controller startup timed out: {sorted(set(robots)-ready)}')
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    raise SystemExit(0 if success else 1)
