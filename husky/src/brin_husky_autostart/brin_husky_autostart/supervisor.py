"""Start one Hokuyo, then Nav2 with the parking pose, then the gated RMF adapter."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseWithCovarianceStamped
from lifecycle_msgs.srv import GetState
from nav_msgs.msg import OccupancyGrid
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String

from .startup import load_settings, prepare


CORE = ('rmf_traffic_schedule_primary', 'rmf_task_dispatcher', 'building_map_server')
NAVIGATION = ('amcl', 'map_server', 'controller_server', 'bt_navigator', 'nav_ekf_node')


def terminate_group(process):
    if process is None or process.poll() is not None:
        return
    for number, timeout in ((signal.SIGINT, 12), (signal.SIGTERM, 3), (signal.SIGKILL, 3)):
        try:
            os.killpg(process.pid, number)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=timeout)
            return
        except subprocess.TimeoutExpired:
            pass
    raise RuntimeError('Bringup child process did not stop')


class Supervisor(Node):
    def __init__(self, settings, prepared, runtime_dir, *, navigation_only=False):
        super().__init__('brin_husky_boot_supervisor')
        self.settings, self.prepared = settings, prepared
        self.runtime_dir = Path(runtime_dir)
        self.navigation_only = navigation_only
        self.stopping = False
        self.children = []
        self.scan_seen = self.pose_seen = self.profile_seen = None
        self.map_message = None
        self.digest = None
        self.lifecycle_state = None
        self.lifecycle_future = None
        self.next_lifecycle = 0.
        latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.subscriptions_owned = [
            self.create_subscription(LaserScan, '/a200_1060/scan', self.on_scan, qos_profile_sensor_data),
            self.create_subscription(OccupancyGrid, '/a200_1060/map', self.on_map, latched),
            self.create_subscription(PoseWithCovarianceStamped, '/a200_1060/amcl_pose',
                                     self.on_pose, qos_profile_sensor_data),
            self.create_subscription(String, '/brin_hardware/profile_digest', self.on_profile, latched)]
        self.lifecycle = self.create_client(GetState, '/a200_1060/bt_navigator/get_state')

    def on_scan(self, message):
        age = self.get_clock().now().nanoseconds / 1e9 - message.header.stamp.sec - message.header.stamp.nanosec / 1e9
        if -0.5 <= age <= 2.0:
            self.scan_seen = time.monotonic()

    def on_map(self, message):
        self.map_message = message

    def on_pose(self, message):
        if message.header.frame_id == 'map':
            self.pose_seen = time.monotonic()

    def on_profile(self, message):
        self.digest = message.data
        self.profile_seen = time.monotonic()

    def status(self, stage, detail):
        self.get_logger().info(f'{stage}: {detail}')
        path = self.runtime_dir/'status.json'
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps({'stage': stage, 'detail': detail,
            'timestamp': time.time(), 'traffic_profile': self.settings['traffic_profile'],
            'initial_pose': self.settings['initial_pose']}, indent=2)+'\n')
        temporary.replace(path)

    def spawn(self, name, arguments):
        self.status(name, 'starting ' + ' '.join(arguments))
        child = subprocess.Popen(arguments, start_new_session=True)
        self.children.append((name, child))
        return child

    def poll(self):
        rclpy.spin_once(self, timeout_sec=0.1)
        for name, process in self.children:
            if name != 'adapter' and process.poll() is not None:
                raise RuntimeError(f'{name} launch exited with {process.returncode}')
        if self.lifecycle_future is not None and self.lifecycle_future.done():
            try:
                self.lifecycle_state = self.lifecycle_future.result().current_state.id
            except Exception:
                self.lifecycle_state = None
            self.lifecycle_future = None
            self.next_lifecycle = time.monotonic()+2.
        if (self.lifecycle_future is None and time.monotonic() >= self.next_lifecycle
                and self.lifecycle.service_is_ready()):
            self.lifecycle_future = self.lifecycle.call_async(GetState.Request())

    def wait(self, condition, stage, detail, timeout=None):
        start, next_log = time.monotonic(), 0.
        while not self.stopping:
            self.poll()
            if condition():
                return True
            now = time.monotonic()
            if timeout is not None and now-start > timeout:
                raise RuntimeError(f'Timed out waiting for {stage}: {detail}')
            if now >= next_log:
                self.status(stage, detail)
                next_log = now+15.
        return False

    def core_ready(self):
        names = [name for name, namespace in self.get_node_names_and_namespaces()]
        return (all(names.count(name) == 1 for name in CORE)
                and self.count_publishers('/brin_hardware/profile_digest') == 1
                and self.profile_seen is not None and time.monotonic()-self.profile_seen < 5.
                and self.digest == self.prepared['profile_digest'])

    def navigation_ready(self):
        return (self.map_message is not None and self.pose_seen is not None
                and self.lifecycle_state == 3
                and self.scan_seen is not None and time.monotonic()-self.scan_seen < 2.)

    def run(self):
        # Allow local DDS discovery before deciding whether a stack already exists.
        self.status('discovery', 'checking for existing physical launches')
        end = time.monotonic()+8.
        while not self.stopping and time.monotonic() < end:
            self.poll()
        if self.stopping:
            return
        nodes = self.get_node_names_and_namespaces()
        existing = [name for name, namespace in nodes
                    if (namespace == '/a200_1060' and name in NAVIGATION)
                    or name in ('brin_physical_tf_bridge', 'brin_husky_fleet_adapter')]
        if existing or self.count_publishers('/a200_1060/map'):
            raise RuntimeError(f'Existing Nav2/integration detected; stop manual launch first: {existing}')
        scans = self.count_publishers('/a200_1060/scan')
        if scans > 1:
            raise RuntimeError('Multiple scan publishers detected')
        if scans == 0:
            self.spawn('hokuyo', ['ros2', 'launch', 'hokuyo_bringup', 'hokuyo_bringup.launch.py'])
        else:
            self.status('hokuyo', 'using the existing single physical scan publisher')
        if not self.wait(lambda: self.scan_seen is not None and time.monotonic()-self.scan_seen < 2.,
                         'scan', 'waiting for fresh Hokuyo data', self.settings['scan_timeout']):
            return
        self.spawn('nav2', ['ros2', 'launch', 'husky_nav2', 'navigation.launch.py',
            'map:='+self.prepared['map'], 'params_file:='+self.prepared['params_file'],
            'use_sim_time:=false', 'start_hokuyo:=false'])
        if not self.wait(self.navigation_ready, 'localization',
                         'waiting for AMCL parking pose, map, scan and active Nav2',
                         self.settings['navigation_timeout']):
            return
        self.status('navigation_ready', 'AMCL initialized; Nav2 active')
        if self.navigation_only:
            while not self.stopping:
                self.poll()
            return
        while not self.stopping:
            if not self.wait(self.core_ready, 'rmf_core',
                             'waiting for komputer-utama core and matching profile digest'):
                return
            if not self.wait(self.navigation_ready, 'navigation', 'waiting for Nav2 readiness',
                             self.settings['navigation_timeout']):
                return
            child = self.spawn('adapter', ['ros2', 'launch', 'brin_husky_distributed',
                'robot.launch.py', 'traffic_profile:='+self.settings['traffic_profile'],
                'hardware_config:='+self.prepared['hardware_config'],
                'startup_fleet_config:='+self.prepared['startup_fleet_config'],
                'start_nav2:=false', 'start_hokuyo:=false', 'enable_dispatch:=true',
                'preflight_timeout:='+str(self.settings['preflight_timeout']),
                'server_uri:='+self.prepared['server_uri']])
            started = time.monotonic()
            missing_since = None
            self.status('preflight_adapter', 'preflight controls adapter activation; no goal is sent by startup')
            while not self.stopping and child.poll() is None:
                self.poll()
                # robot.launch retains the bridge if the adapter process dies.
                # Recycle that launch rather than creating a second bridge.
                if time.monotonic()-started > self.settings['preflight_timeout']+120.:
                    names = [name for name, _ in self.get_node_names_and_namespaces()]
                    if 'brin_husky_fleet_adapter' not in names:
                        missing_since = missing_since or time.monotonic()
                        if time.monotonic()-missing_since > 10.:
                            self.status('adapter_retry', 'adapter exited; recycling its launch')
                            break
                    else:
                        missing_since = None
            terminate_group(child)
            self.children.remove(('adapter', child))
            end = time.monotonic()+self.settings['retry_delay']
            while not self.stopping and time.monotonic()<end:
                self.poll()

    def close(self):
        for _, child in reversed(self.children):
            terminate_group(child)
        self.status('stopped', 'owned processes stopped')
        self.destroy_node()


def main(args=None):
    share = Path(get_package_share_directory('brin_husky_autostart'))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(share/'config/bringup.yaml'))
    parser.add_argument('--runtime-dir', required=True)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--navigation-only', action='store_true',
                        help='Validate sensor/Nav2 startup without activating an adapter')
    options = parser.parse_args(args)
    output = Path(options.runtime_dir)
    output.mkdir(parents=True, exist_ok=True)
    with (output/'bringup.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Husky boot supervisor already running')
        settings = load_settings(options.config)
        nav2 = Path(get_package_share_directory('husky_nav2'))/'config/nav2_params.yaml'
        distributed = Path(get_package_share_directory('brin_husky_distributed'))
        prepared = prepare(settings, nav2, output,
                           hardware_source=distributed/'config/husky_0.yaml',
                           fleet_source=distributed/'config/fleet_config.yaml')
        if options.prepare_only:
            print(json.dumps(prepared, indent=2))
            return
        if os.environ.get('BRIN_ENABLE_DISPATCH') != '1' and not options.navigation_only:
            raise SystemExit('Boot adapter requires BRIN_ENABLE_DISPATCH=1')
        rclpy.init(args=[], signal_handler_options=SignalHandlerOptions.NO)
        node = Supervisor(settings, prepared, output, navigation_only=options.navigation_only)
        def stop(_number, _frame):
            node.stopping = True
        previous = {number: signal.signal(number, stop) for number in (signal.SIGINT, signal.SIGTERM)}
        try:
            node.run()
        finally:
            try:
                node.close()
            finally:
                for number, handler in previous.items():
                    signal.signal(number, handler)
                if rclpy.ok():
                    rclpy.shutdown()
