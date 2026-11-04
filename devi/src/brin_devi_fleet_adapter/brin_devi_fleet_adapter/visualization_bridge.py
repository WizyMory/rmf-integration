"""Read-only Nav2 telemetry for RViz, isolated from every motion gateway."""
from copy import deepcopy
import fcntl
import multiprocessing
import os
from pathlib import Path
import signal

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from geometry_msgs.msg import PoseWithCovarianceStamped, PolygonStamped
from nav_msgs.msg import OccupancyGrid, Odometry, Path as NavPath
from nav2_msgs.msg import ParticleCloud
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage


# Only observed telemetry belongs here. No goals, cmd_vel, lifecycle changes,
# initial poses, parameter setters, or control TF topics are published.
STREAMS = {
    'scan': (LaserScan, '/devi/rplidar/scan_filtered', 'scan', False),
    'scan_raw': (LaserScan, '/devi/rplidar/scan', 'scan_raw', False),
    'global_costmap': (OccupancyGrid, '/global_costmap/costmap', 'global_costmap/costmap', True),
    'local_costmap': (OccupancyGrid, '/local_costmap/costmap', 'local_costmap/costmap', True),
    'global_footprint': (PolygonStamped, '/global_costmap/published_footprint', 'global_costmap/footprint', False),
    'local_footprint': (PolygonStamped, '/local_costmap/published_footprint', 'local_costmap/footprint', False),
    'amcl': (PoseWithCovarianceStamped, '/amcl_pose', 'amcl_pose', True),
    'particles': (ParticleCloud, '/particle_cloud', 'particle_cloud', False),
    'odom': (Odometry, '/odometry/filtered', 'odometry', False),
    'plan': (NavPath, '/plan', 'plan', False),
    'local_plan': (NavPath, '/local_plan', 'local_plan', False),
    'smoothed_plan': (NavPath, '/plan_smoothed', 'plan_smoothed', False),
    'received_plan': (NavPath, '/received_global_plan', 'received_global_plan', False),
    'description': (String, '/devi/robot_description', 'robot_description', True),
    'tf': (TFMessage, '/tf', 'tf', False),
    'tf_static': (TFMessage, '/tf_static', 'tf_static', True),
}


def display_frame(frame):
    frame = frame.lstrip('/')
    return frame if not frame or frame == 'map' or frame.startswith('devi/') else 'devi/' + frame


def display_message(message):
    """Copy only frame labels; coordinates, sensor values and stamps stay real."""
    result = deepcopy(message)

    def visit(value):
        if hasattr(value, 'get_fields_and_field_types'):
            for field in value.get_fields_and_field_types():
                child = getattr(value, field)
                if field in ('frame_id', 'child_frame_id') and isinstance(child, str):
                    setattr(value, field, display_frame(child))
                else:
                    visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                if hasattr(child, 'get_fields_and_field_types'):
                    visit(child)
    visit(result)
    return result


def stream_qos(durable=False, depth=1):
    return QoSProfile(depth=depth,
        reliability=ReliabilityPolicy.RELIABLE if durable else ReliabilityPolicy.BEST_EFFORT,
        durability=DurabilityPolicy.TRANSIENT_LOCAL if durable else DurabilityPolicy.VOLATILE)


class LatestTelemetry:
    """Bounded latest values; TF from multiple publishers forms one full tree."""
    def __init__(self):
        self.latest = {}
        self.transforms = {'tf': {}, 'tf_static': {}}

    def receive(self, key, message):
        if key in self.transforms:
            self.transforms[key].update({item.child_frame_id: item for item in message.transforms})
            self.latest[key] = TFMessage(transforms=list(self.transforms[key].values()))
        else:
            self.latest[key] = message

    def take(self):
        batch, self.latest = self.latest, {}
        return batch


def telemetry_worker(connection):
    os.environ['RMW_IMPLEMENTATION'] = 'rmw_fastrtps_cpp'
    os.environ['ROS_DOMAIN_ID'] = '73'
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    from rclpy.signals import SignalHandlerOptions
    rclpy.init(args=[], domain_id=73, signal_handler_options=SignalHandlerOptions.NO)
    node = Node('devi_visualization_source', use_global_arguments=False)
    cache = LatestTelemetry()
    subscriptions = [node.create_subscription(kind, topic,
        lambda msg, k=key: cache.receive(k, msg), stream_qos(durable, 100 if key.startswith('tf') else 1))
        for key, (kind, topic, _, durable) in STREAMS.items()]
    # TF can have several independent publishers; retain enough startup samples.
    # All samples are accumulated by child frame before the next pull.
    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.01)
            if connection.poll():
                operation = connection.recv()
                if operation == 'close':
                    break
                if operation == 'poll':
                    connection.send(cache.take())
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
        connection.close()


class VisualizationBridge(Node):
    def __init__(self):
        super().__init__('devi_visualization_bridge')
        self.publishers_by_key = {key: self.create_publisher(kind, '/devi/viz/' + suffix,
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL
                       if durable else DurabilityPolicy.VOLATILE))
            for key, (kind, _, suffix, durable) in STREAMS.items()}
        context = multiprocessing.get_context('spawn')
        self.connection, child = context.Pipe()
        self.worker = context.Process(target=telemetry_worker, args=(child,))
        self.worker.start()
        child.close()
        self.pending = False
        self.timer = self.create_timer(0.1, self.poll)
        self.get_logger().info('Read-only Devi telemetry: /devi/viz/*, frames devi/*, shared map')

    def poll(self):
        if not self.worker.is_alive():
            raise RuntimeError('Devi visualization source exited')
        if self.pending and self.connection.poll():
            batch = self.connection.recv()
            self.pending = False
            for key, message in batch.items():
                if key in self.publishers_by_key:
                    self.publishers_by_key[key].publish(display_message(message))
        if not self.pending:
            self.connection.send('poll')
            self.pending = True

    def close(self):
        previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            try:
                # Drain the single outstanding pull before requesting shutdown.
                if self.connection.poll(0.2):
                    self.connection.recv()
                self.connection.send('close')
            except (BrokenPipeError, OSError):
                pass
            self.worker.join(timeout=3.)
            if self.worker.is_alive():
                self.worker.terminate()
                self.worker.join(timeout=2.)
        finally:
            self.connection.close()
            signal.signal(signal.SIGINT, previous)


def main(args=None):
    # This lock also protects a temporary standalone bridge until next boot,
    # when bringup.launch.py takes over. Duplicate telemetry is never needed.
    lock_path = Path(__file__).resolve().parents[3]/'log/visualization_bridge.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Devi visualization bridge already running', flush=True)
            return
        rclpy.init(args=args, domain_id=0)
        node = None
        try:
            node = VisualizationBridge()
            rclpy.spin(node)
        except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
            pass
        finally:
            if node is not None:
                node.close()
                node.destroy_node()
            rclpy.try_shutdown()
