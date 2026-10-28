"""Read-only physical Husky gate: no velocity commands and no Nav2 goals."""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from controller_manager_msgs.srv import ListControllers
from lifecycle_msgs.msg import State
from lifecycle_msgs.srv import GetState
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid, Odometry
from PIL import Image
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import Imu, LaserScan
from std_msgs.msg import Bool, String
from tf2_ros import Buffer, TransformException, TransformListener
import yaml


def expected_map(path):
    path = Path(path)
    config = yaml.safe_load(path.read_text())
    with Image.open(path.parent / config['image']) as image:
        width, height = image.size
    return {
        'width': width, 'height': height,
        'resolution': float(config['resolution']),
        'origin': [float(x) for x in config['origin']],
    }


def map_geometry_errors(message, expected, map_frame='map'):
    info = message.info
    actual = (info.width, info.height, info.resolution)
    desired = (expected['width'], expected['height'], expected['resolution'])
    errors = []
    if (actual[:2] != desired[:2]
            or not math.isclose(actual[2], desired[2], abs_tol=1e-6)):
        errors.append(f'Nav2 map geometry {actual} differs from BRIN {desired}')
    origin = info.origin
    yaw = math.atan2(
        2 * (origin.orientation.w * origin.orientation.z
             + origin.orientation.x * origin.orientation.y),
        1 - 2 * (origin.orientation.y ** 2 + origin.orientation.z ** 2))
    pose = (origin.position.x, origin.position.y, yaw)
    if any(not math.isclose(a, b, abs_tol=1e-3)
           for a, b in zip(pose, expected['origin'])):
        errors.append(f'Nav2 map origin {pose} differs from BRIN {expected["origin"]}')
    if message.header.frame_id != map_frame:
        errors.append(f'Nav2 map frame {message.header.frame_id} differs from {map_frame}')
    return errors


def distance_to_graph(graph_path, map_name, x, y):
    graph = (yaml.safe_load(Path(graph_path).read_text())
             if isinstance(graph_path, (str, Path)) else graph_path)
    level = graph['levels'][map_name]
    vertices = level['vertices']
    distances = []
    for start, end, *_ in level['lanes']:
        ax, ay = vertices[start][:2]
        bx, by = vertices[end][:2]
        dx, dy = bx - ax, by - ay
        fraction = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy)
                                 / (dx * dx + dy * dy))) if dx or dy else 0.0
        distances.append(math.hypot(x - (ax + fraction * dx),
                                    y - (ay + fraction * dy)))
    return min(distances) if distances else math.inf


RMF_CORE_NODES = ('rmf_traffic_schedule_primary', 'rmf_task_dispatcher',
                  'building_map_server')


def existing_rmf_processes(nodes):
    return sorted(name for name, _namespace in nodes
                  if name.startswith('rmf_traffic_schedule')
                  or name in ('rmf_task_dispatcher', 'building_map_server',
                              'brin_husky_fleet_adapter', 'husky_rmf_nav2_adapter'))


def unexpected_rmf_processes(nodes, allow_rmf_core=False):
    existing = existing_rmf_processes(nodes)
    if allow_rmf_core:
        existing = [name for name in existing if name not in RMF_CORE_NODES]
    return existing


def rmf_core_errors(nodes):
    names = [name for name, _namespace in nodes]
    return [f'Expected exactly one {name}, found {names.count(name)}'
            for name in RMF_CORE_NODES if names.count(name) != 1]


def profile_match_errors(expected, seen, last_seen, publishers, now=None):
    if not expected:
        return []
    current = time.monotonic() if now is None else now
    errors = []
    if publishers != 1:
        errors.append('Expected exactly one laptop profile publisher')
    if last_seen is None or current - last_seen > 5.0:
        errors.append('Laptop profile announcement unavailable or stale')
    elif seen != {expected}:
        errors.append('Laptop and Husky map/graph profile digests differ '
                      f'(Husky expected {expected}; laptop observed {sorted(seen)})')
    return errors


class NativeControllerProbe:
    """Read Clearpath's service with a separate RMW, without changing this node."""

    def __init__(self, service, rmw):
        self.service = service
        self.rmw = rmw
        self.process = None
        self.started_at = None
        self.next_at = 0.0
        self.controllers = None
        self.last_success = None

    def poll(self):
        now = time.monotonic()
        if self.process is not None:
            if self.process.poll() is None and now - self.started_at > 12.0:
                self.process.terminate()
                try:
                    self.process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            if self.process.poll() is not None:
                output, error = self.process.communicate()
                if self.process.returncode == 0:
                    try:
                        controllers = json.loads(output.splitlines()[-1])
                        if (not isinstance(controllers, dict)
                                or not all(isinstance(name, str) and isinstance(state, str)
                                           for name, state in controllers.items())):
                            raise ValueError('Invalid controller probe response')
                        self.controllers = controllers
                        self.last_success = now
                        error = ''
                    except (ValueError, TypeError, IndexError) as exc:
                        error = str(exc)
                self.process = None
                self.next_at = now + 5.0
                if error:
                    return error.strip()
        if self.process is None and now >= self.next_at:
            env = os.environ.copy()
            env['RMW_IMPLEMENTATION'] = self.rmw
            if self.rmw != 'rmw_cyclonedds_cpp':
                env.pop('CYCLONEDDS_URI', None)
            try:
                self.process = subprocess.Popen(
                    [sys.executable, '-m', 'brin_husky_hardware.controller_probe',
                     self.service], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, env=env)
                self.started_at = now
            except OSError as exc:
                self.next_at = now + 5.0
                return str(exc)
        return None

    def current(self):
        if self.last_success is None or time.monotonic() - self.last_success > 15.0:
            return None
        return self.controllers

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if self.process is not None:
            self.process.communicate()
            self.process = None


class HardwarePreflight(Node):
    def __init__(self):
        super().__init__('brin_hardware_preflight')
        for name, default in (
            ('config_file', ''), ('map_yaml', ''), ('nav_graph', ''),
            ('map_name', 'L1'), ('timeout', 45.0),
            ('allow_rmf_core', False), ('require_rmf_core', False),
            ('profile_digest', ''), ('controller_probe_rmw', '')):
            self.declare_parameter(name, default)
        self.config = yaml.safe_load(Path(self.get_parameter('config_file').value).read_text())
        self.map_expected = expected_map(self.get_parameter('map_yaml').value)
        self.graph_path = self.get_parameter('nav_graph').value
        self.graph = yaml.safe_load(Path(self.graph_path).read_text())
        self.map_name = self.get_parameter('map_name').value
        self.robot_name = self.config['robot_name']
        self.namespace = self.config['ros_namespace']
        self.map_frame = self.config.get('map_frame', 'map')
        self.tf = Buffer()
        self.listener = TransformListener(self.tf, self)
        self.map_msg = self.scan_msg = self.odom_msg = self.imu_msg = None
        self.tf_conflict = None
        self.profile_digest = self.get_parameter('profile_digest').value
        self.profile_seen = set()
        self.profile_last_seen = None
        if self.profile_digest:
            self.profile_subscription = self.create_subscription(
                String, '/brin_hardware/profile_digest', self.on_profile,
                QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                           durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.status_subscription = self.create_subscription(
            Bool, f'/{self.robot_name}/hardware_tf_conflict',
            self.on_status,
            QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.map_subscription = self.create_subscription(
            OccupancyGrid, self.config['map_topic'], self.on_map,
            QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.scan_subscription = self.create_subscription(
            LaserScan, f'/{self.robot_name}/scan',
            self.on_scan, qos_profile_sensor_data)
        self.odom_subscription = self.create_subscription(
            Odometry, f'/{self.robot_name}/platform/odom/filtered',
            self.on_odom, qos_profile_sensor_data)
        self.imu_subscription = self.create_subscription(
            Imu, f'/{self.robot_name}/sensors/imu_0/data',
            self.on_imu, qos_profile_sensor_data)
        self.navigate = ActionClient(
            self, NavigateToPose, f'/{self.namespace}/navigate_to_pose')
        controller_service = self.config['controller_manager'] + '/list_controllers'
        probe_rmw = self.get_parameter('controller_probe_rmw').value
        self.native_controller_probe = (NativeControllerProbe(controller_service, probe_rmw)
                                        if probe_rmw else None)
        self.controller = (None if self.native_controller_probe else
                           self.create_client(ListControllers, controller_service))
        self.lifecycle = self.create_client(
            GetState, f'/{self.namespace}/bt_navigator/get_state')
        self.controller_future = self.lifecycle_future = None
        self.controllers = self.navigation_state = None

    def on_map(self, message):
        self.map_msg = message

    def on_scan(self, message):
        self.scan_msg = message

    def on_odom(self, message):
        self.odom_msg = message

    def on_imu(self, message):
        self.imu_msg = message

    def on_status(self, message):
        self.tf_conflict = message.data

    def on_profile(self, message):
        self.profile_seen.add(message.data)
        self.profile_last_seen = time.monotonic()

    def poll_services(self):
        if self.native_controller_probe:
            error = self.native_controller_probe.poll()
            if error:
                self.get_logger().warn(f'Native controller probe: {error}')
            self.controllers = self.native_controller_probe.current()
        elif self.controller_future is None and self.controller.service_is_ready():
            self.controller_future = self.controller.call_async(ListControllers.Request())
        if self.lifecycle_future is None and self.lifecycle.service_is_ready():
            self.lifecycle_future = self.lifecycle.call_async(GetState.Request())
        if self.controller_future is not None and self.controller_future.done():
            try:
                self.controllers = {item.name: item.state for item in
                                    self.controller_future.result().controller}
            except Exception:
                self.controllers = {}
            self.controller_future = None
        if self.lifecycle_future is not None and self.lifecycle_future.done():
            try:
                self.navigation_state = self.lifecycle_future.result().current_state.id
            except Exception:
                self.navigation_state = -1
            self.lifecycle_future = None

    def check(self):
        errors = []
        nodes = self.get_node_names_and_namespaces()
        require_core = self.get_parameter('require_rmf_core').value
        existing = unexpected_rmf_processes(
            nodes, self.get_parameter('allow_rmf_core').value or require_core)
        if existing:
            errors.append(f'Existing RMF nodes on this domain: {existing}')
        if require_core:
            errors += rmf_core_errors(nodes)
        if self.profile_digest:
            errors += profile_match_errors(
                self.profile_digest, self.profile_seen, self.profile_last_seen,
                self.count_publishers('/brin_hardware/profile_digest'))
        if self.tf_conflict is None:
            errors.append('TF bridge status unavailable')
        elif self.tf_conflict:
            errors.append('More than one TF authority for a robot frame')
        if self.map_msg is None:
            errors.append(f'No map on {self.config["map_topic"]}')
        else:
            errors += map_geometry_errors(self.map_msg, self.map_expected, self.map_frame)
        now = self.get_clock().now()
        for label, message in (('scan', self.scan_msg),
                               ('odometry', self.odom_msg), ('IMU', self.imu_msg)):
            if message is None:
                errors.append(f'No {label} from physical robot')
                continue
            age = (now - Time.from_msg(message.header.stamp)).nanoseconds / 1e9
            if not -0.5 <= age <= self.config.get('max_tf_age', 2.0):
                errors.append(f'Stale {label}: {age:.2f}s')
        if self.odom_msg is not None and (
                self.odom_msg.header.frame_id != self.robot_name + '/odom'
                or self.odom_msg.child_frame_id != self.robot_name + '/' +
                self.config.get('base_frame', 'base_link')):
            errors.append('Prefixed odometry frames differ from configured odom/base_link')
        pose = None
        try:
            transform = self.tf.lookup_transform(
                self.map_frame, self.robot_name + '/' + self.config['base_frame'], Time())
            age = (now - Time.from_msg(transform.header.stamp)).nanoseconds / 1e9
            if not -0.5 <= age <= self.config.get('max_tf_age', 2.0):
                errors.append(f'Stale map-to-base TF: {age:.2f}s')
            else:
                point = transform.transform.translation
                pose = [point.x, point.y]
                distance = distance_to_graph(
                    self.graph, self.map_name, point.x, point.y)
                if distance > self.config.get('max_graph_distance', 1.0):
                    errors.append(f'Robot is {distance:.2f}m from RMF graph')
        except TransformException as exc:
            errors.append(f'Missing map-to-{self.robot_name}/base_link TF: {exc}')
        if self.scan_msg is not None:
            try:
                self.tf.lookup_transform(
                    self.robot_name + '/' + self.config['base_frame'],
                    self.scan_msg.header.frame_id,
                    Time())
            except TransformException as exc:
                errors.append(f'Missing prefixed laser TF: {exc}')
        if self.imu_msg is not None:
            try:
                self.tf.lookup_transform(
                    self.robot_name + '/' + self.config['base_frame'],
                    self.imu_msg.header.frame_id,
                    Time())
            except TransformException as exc:
                errors.append(f'Missing prefixed IMU TF: {exc}')
        if self.controllers is None:
            errors.append('Controller manager unavailable')
        elif self.controllers.get('platform_velocity_controller') != 'active':
            errors.append('Platform velocity controller not active')
        if self.navigation_state != State.PRIMARY_STATE_ACTIVE:
            errors.append('Nav2 bt_navigator not active')
        if not self.navigate.server_is_ready():
            errors.append('NavigateToPose action unavailable')
        return {'robot': self.robot_name, 'physical_namespace': self.namespace,
                'pose_xy': pose, 'errors': errors, 'accepted': not errors}

    def run(self):
        deadline = time.monotonic() + float(self.get_parameter('timeout').value)
        report = None
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            self.poll_services()
            report = self.check()
            if report['accepted']:
                break
        print(json.dumps(report, indent=2), flush=True)
        return 0 if report and report['accepted'] else 1


def main(args=None):
    rclpy.init(args=args)
    node = HardwarePreflight()
    try:
        result = node.run()
    finally:
        if node.native_controller_probe:
            node.native_controller_probe.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    raise SystemExit(result)
