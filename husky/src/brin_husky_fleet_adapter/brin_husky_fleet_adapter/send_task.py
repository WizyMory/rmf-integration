"""Send a patrol through installed RMF's task API, or cancel an existing task."""
import argparse
from pathlib import Path
import yaml
from ament_index_python.packages import get_package_share_directory
import json
import time
import uuid
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from rmf_task_msgs.msg import ApiRequest, ApiResponse


def main(args=None):
    import sys
    argv = sys.argv if args is None else [sys.argv[0]]+args
    p = argparse.ArgumentParser(description=__doc__)
    fleet_config = yaml.safe_load((Path(get_package_share_directory(
        'brin_husky_fleet_adapter'))/'config/fleet_config.yaml').read_text())
    p.add_argument('--robot', choices=sorted(fleet_config['robots']))
    p.add_argument('--places', nargs='+')
    p.add_argument('--cancel', metavar='TASK_ID')
    p.add_argument('--timeout', type=float, default=30.0)
    a = p.parse_args(rclpy.utilities.remove_ros_args(argv)[1:])
    if not a.cancel and not a.places:
        p.error('--places or --cancel is required')
    rclpy.init(args=argv)
    node = Node('brin_task_requester', parameter_overrides=[rclpy.Parameter('use_sim_time', value=True)])
    qos = QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                     reliability=ReliabilityPolicy.RELIABLE)
    pub = node.create_publisher(ApiRequest, '/task_api_requests', qos)
    request_id = 'brin_'+str(uuid.uuid4())
    responses = []
    def response(msg):
        if msg.request_id == request_id and msg.type == ApiResponse.TYPE_RESPONDING:
            responses.append(json.loads(msg.json_msg))
    node.create_subscription(ApiResponse, '/task_api_responses', response, qos)
    deadline = time.monotonic()+a.timeout
    while rclpy.ok() and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
        if pub.get_subscription_count() and node.get_clock().now().nanoseconds > 0:
            break
    if a.cancel:
        payload = {'type': 'cancel_task_request', 'task_id': a.cancel, 'labels': ['BRIN test cancellation']}
    else:
        payload = {'type': 'robot_task_request' if a.robot else 'dispatch_task_request',
                   'request': {'category': 'patrol',
                               'description': {'places': a.places, 'rounds': 1},
                               'unix_millis_earliest_start_time': node.get_clock().now().nanoseconds//1000000}}
        if a.robot:
            payload.update(fleet='HuskyA200', robot=a.robot)
    pub.publish(ApiRequest(request_id=request_id, json_msg=json.dumps(payload)))
    print(json.dumps(payload, indent=2), flush=True)
    while rclpy.ok() and not responses and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_node()
    rclpy.shutdown()
    if not responses:
        raise SystemExit('Timed out waiting for RMF API response')
    print(json.dumps(responses[0], indent=2))
    if responses[0].get('success') is False:
        raise SystemExit(1)
