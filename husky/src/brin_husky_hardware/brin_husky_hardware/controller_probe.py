"""Query the Clearpath controller service in its own DDS participant."""
import json
import sys

from controller_manager_msgs.srv import ListControllers
import rclpy
from rclpy.node import Node


def main(args=None):
    service = (sys.argv[1] if args is None else args[0])
    rclpy.init(args=[])
    node = Node('brin_controller_probe')
    try:
        client = node.create_client(ListControllers, service)
        if not client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError(f'Controller service unavailable: {service}')
        future = client.call_async(ListControllers.Request())
        rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
        if not future.done():
            raise RuntimeError(f'Controller service did not respond: {service}')
        response = future.result()
        if response is None:
            raise RuntimeError(f'Controller service returned no result: {service}')
        print(json.dumps({item.name: item.state for item in response.controller}),
              flush=True)
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
