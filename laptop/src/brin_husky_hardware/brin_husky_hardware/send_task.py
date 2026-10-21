"""Wall-time RMF Patrol request and cancellation for the physical Husky."""
import argparse
import json
import time
import uuid

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rmf_task_msgs.msg import ApiRequest, ApiResponse


def request_payload(places, robot, cancel_id, now_ns):
    if cancel_id:
        return {'type': 'cancel_task_request', 'task_id': cancel_id,
                'labels': ['BRIN physical task cancellation']}
    payload = {
        'type': 'robot_task_request' if robot else 'dispatch_task_request',
        'request': {'category': 'patrol',
                    'description': {'places': places, 'rounds': 1},
                    'unix_millis_earliest_start_time': now_ns // 1_000_000},
    }
    if robot:
        payload.update(fleet='HuskyA200', robot=robot)
    return payload


def main(args=None):
    import sys
    argv = sys.argv if args is None else [sys.argv[0]] + args
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--robot', choices=['husky_0'])
    parser.add_argument('--places', nargs='+')
    parser.add_argument('--cancel', metavar='TASK_ID')
    parser.add_argument('--timeout', type=float, default=30.0)
    options = parser.parse_args(rclpy.utilities.remove_ros_args(argv)[1:])
    if not options.cancel and not options.places:
        parser.error('--places or --cancel is required')
    rclpy.init(args=argv)
    node = Node('brin_hardware_task_requester', parameter_overrides=[
        rclpy.Parameter('use_sim_time', value=False)])
    qos = QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                     reliability=ReliabilityPolicy.RELIABLE)
    publisher = node.create_publisher(ApiRequest, '/task_api_requests', qos)
    responses = []
    request_id = 'brin_hardware_' + str(uuid.uuid4())

    def receive(message):
        if message.request_id == request_id and message.type == ApiResponse.TYPE_RESPONDING:
            responses.append(json.loads(message.json_msg))

    subscription = node.create_subscription(
        ApiResponse, '/task_api_responses', receive, qos)
    deadline = time.monotonic() + options.timeout
    try:
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            if publisher.get_subscription_count():
                break
        if not publisher.get_subscription_count():
            raise SystemExit('RMF task API unavailable')
        payload = request_payload(
            options.places, options.robot, options.cancel,
            node.get_clock().now().nanoseconds)
        publisher.publish(ApiRequest(
            request_id=request_id, json_msg=json.dumps(payload)))
        print(json.dumps(payload, indent=2), flush=True)
        while rclpy.ok() and not responses and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        if not responses:
            raise SystemExit('Timed out waiting for RMF API response')
        print(json.dumps(responses[0], indent=2))
        if responses[0].get('success') is False:
            raise SystemExit(1)
    finally:
        node.destroy_subscription(subscription)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
