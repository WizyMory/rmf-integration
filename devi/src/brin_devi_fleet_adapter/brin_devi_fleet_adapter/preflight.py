"""Read-only readiness inspection; creates no goals, cmd_vel or TF publishers."""
import argparse
import json
import math
from pathlib import Path
import time

import yaml
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, qos_profile_sensor_data
from rclpy.time import Time
from geometry_msgs.msg import PoseWithCovarianceStamped
from lifecycle_msgs.srv import GetState
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid, Odometry
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String
from tf2_ros import Buffer, TransformListener, TransformException

from .domains import RmfObserver
from .geometry import MapAlignment, require_commissioning
from .profiles import load_settings, resolve_profile


class Inspection(Node):
    def __init__(self, settings):
        super().__init__('devi_preflight')
        self.settings = settings
        self.messages = {}
        self.subscriptions_keep = []
        durable = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        for key, msgtype, qos in (
                ('map', OccupancyGrid, durable), ('scan', LaserScan, qos_profile_sensor_data),
                ('odom', Odometry, qos_profile_sensor_data),
                ('amcl', PoseWithCovarianceStamped, durable)):
            self.subscriptions_keep.append(self.create_subscription(
                msgtype, settings[key + '_topic'],
                lambda msg, k=key: self.messages.__setitem__(k, msg), qos))
        self.tf = Buffer()
        self.listener = TransformListener(self.tf, self)
        self.action = ActionClient(self, NavigateToPose, settings['navigate_action'])
        self.lifecycle = {}
        for name in ('bt_navigator', 'controller_server', 'planner_server',
                     'behavior_server', 'velocity_smoother'):
            self.lifecycle[name] = {
                'client': self.create_client(GetState, '/' + name + '/get_state'),
                'future': None, 'sent_at': 0., 'observed': None}

    def poll(self):
        rclpy.spin_once(self, timeout_sec=0.05)
        now = time.monotonic()
        for state in self.lifecycle.values():
            client, future = state['client'], state['future']
            if future is not None and future.done():
                try:
                    state['observed'] = future.result().current_state.id
                except Exception:
                    state['observed'] = None
                state['future'] = None
            elif future is not None and now - state['sent_at'] > 2.:
                # Discovery may expose a service before its response endpoints
                # match. Retry read-only queries instead of waiting forever on
                # the first request. Never change lifecycle state.
                future.cancel()
                state['future'] = None
                state['observed'] = None
            if (state['future'] is None and now - state['sent_at'] >= 1.
                    and client.service_is_ready()):
                state['future'] = client.call_async(GetState.Request())
                state['sent_at'] = now

    def report(self):
        errors = []
        for key in ('map', 'scan', 'odom', 'amcl'):
            if key not in self.messages:
                errors.append('Missing topic data: ' + key)
        for key in ('scan', 'odom'):
            if key in self.messages:
                age = (self.get_clock().now() - Time.from_msg(
                    self.messages[key].header.stamp)).nanoseconds / 1e9
                if not -0.5 <= age <= self.settings['max_data_age']:
                    errors.append('Stale topic data: ' + key)
        if not self.action.server_is_ready():
            errors.append('NavigateToPose action unavailable')
        states = {}
        for name, state in self.lifecycle.items():
            states[name] = state['observed']
            if states[name] != 3:
                errors.append('Nav2 lifecycle not active: ' + name)
        pose = None
        try:
            transform = self.tf.lookup_transform(
                self.settings['map_frame'], self.settings['base_frame'], Time())
            age = (self.get_clock().now() - Time.from_msg(transform.header.stamp)).nanoseconds / 1e9
            if not -0.5 <= age <= self.settings['max_data_age']:
                errors.append('Stale localization TF')
            t, q = transform.transform.translation, transform.transform.rotation
            pose = [t.x, t.y, math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))]
        except TransformException:
            errors.append('Missing map to base_link TF')
        map_path = Path(self.settings['nav2_map'])
        if not map_path.is_file():
            errors.append('Missing original Devi map YAML')
        elif 'map' in self.messages:
            metadata = yaml.safe_load(map_path.read_text())
            info = self.messages['map'].info
            yaw = math.atan2(2*info.origin.orientation.w*info.origin.orientation.z,
                             1-2*info.origin.orientation.z**2)
            expected = [metadata['resolution'], *metadata['origin']]
            actual = [info.resolution, info.origin.position.x, info.origin.position.y, yaw]
            if any(abs(a-b) > 1e-5 for a, b in zip(expected, actual)):
                errors.append('Active /map geometry differs from original Devi map')
        return {'nav2_ready': not errors, 'nav2_pose': pose, 'lifecycle': states,
                'nav2_errors': errors, 'robot_domain_id': 73,
                'nav2_action_available': self.action.server_is_ready()}


def integration_report(nav2_report, settings, received_digest, nodes):
    errors = list(nav2_report['nav2_errors'])
    pose = nav2_report['nav2_pose']
    profile = resolve_profile()
    if received_digest != profile['digest']:
        errors.append('Laptop RMF profile absent or differs from gedungWS_0 bundle')
    for name in ('rmf_traffic_schedule_primary', 'rmf_task_dispatcher', 'building_map_server'):
        if nodes.count(name) != 1:
            errors.append('Expected exactly one laptop RMF node: ' + name)
    try:
        require_commissioning(settings)
        if pose is not None:
            rmf_pose = MapAlignment(settings['map_alignment']).to_rmf(pose)
            graph = yaml.safe_load(Path(profile['graph']).read_text())
            level = graph['levels']['L1']
            vertices = level['vertices']
            distances = [math.hypot(v[0]-rmf_pose[0], v[1]-rmf_pose[1]) for v in vertices]
            # Check distance to lanes as well as vertices.
            for source, target, *_ in level['lanes']:
                a, b = vertices[source], vertices[target]
                dx, dy = b[0]-a[0], b[1]-a[1]
                length = dx*dx+dy*dy
                u = max(0., min(1., ((rmf_pose[0]-a[0])*dx+(rmf_pose[1]-a[1])*dy)/length)) if length else 0.
                distances.append(math.hypot(rmf_pose[0]-a[0]-u*dx, rmf_pose[1]-a[1]-u*dy))
            if not distances or min(distances) > settings['max_graph_distance']:
                errors.append('Devi pose is too far from the RMF graph')
    except ValueError as exc:
        errors.append(str(exc))
    return {**nav2_report, 'accepted': not errors, 'robot': 'devi', 'rmf_domain_id': 0,
            'profile_digest': profile['digest'], 'received_profile_digest': received_digest,
            'errors': errors, 'robot_registered': False, 'goals_sent': 0}


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--timeout', type=float, default=12.)
    parser.add_argument('--inspect', action='store_true')
    parsed = parser.parse_args(args)
    if not 1 <= parsed.timeout <= 60:
        parser.error('timeout must be between 1 and 60 seconds')
    settings = load_settings(parsed.config)
    from .gateway import Nav2Gateway
    gateway = Nav2Gateway(settings)
    observer = RmfObserver()
    received = []
    durable = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    subscription = observer.node.create_subscription(
        String, '/brin_hardware/profile_digest', lambda msg: received.append(msg.data), durable)
    try:
        deadline = time.monotonic() + parsed.timeout
        while time.monotonic() < deadline:
            observer.executor.spin_once(timeout_sec=0.05)
            gateway.poll()
        nav2_report = gateway.state if gateway.fresh else {
            'nav2_ready': False, 'nav2_pose': None, 'lifecycle': {},
            'nav2_errors': ['Nav2 gateway unavailable or stale'], 'robot_domain_id': 73}
        report = integration_report(nav2_report, settings, received[-1] if received else None,
                                    observer.node.get_node_names())
        print(json.dumps(report, indent=2), flush=True)
        return 0 if (report['nav2_ready'] if parsed.inspect else report['accepted']) else 2
    finally:
        gateway.close()
        observer.close()
