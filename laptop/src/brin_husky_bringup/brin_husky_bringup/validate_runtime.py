"""Read-only runtime acceptance probe. Exit nonzero on missing data or bad TF."""
import argparse
from pathlib import Path
import yaml
from ament_index_python.packages import get_package_share_directory
import json
import time
import rclpy
from rclpy.node import Node
from rclpy.time import Time
from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy
from sensor_msgs.msg import LaserScan, Imu
from nav_msgs.msg import Odometry
from tf2_msgs.msg import TFMessage
from tf2_ros import Buffer, TransformListener, TransformException
from rmf_fleet_msgs.msg import FleetState


def main(args=None):
    import sys
    argv = sys.argv if args is None else [sys.argv[0]]+args
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--duration', type=float, default=20.0)
    p.add_argument('--require-rmf', action='store_true')
    expected = sorted(yaml.safe_load((Path(get_package_share_directory(
        'brin_rmf_maps'))/'maps/spawns.yaml').read_text()))
    p.add_argument('--robots', nargs='+', choices=expected, default=expected)
    a = p.parse_args(rclpy.utilities.remove_ros_args(argv)[1:])
    rclpy.init(args=argv)
    node = Node('brin_runtime_validator', parameter_overrides=[rclpy.Parameter('use_sim_time', value=True)])
    buffer = Buffer()
    listener = TransformListener(buffer, node)
    received, bad, parents, counts, fleet_robots = {}, set(), {}, {}, set()
    def record(name, kind, msg):
        received[name+'/'+kind] = msg.header.frame_id
        counts[name+'/'+kind] = counts.get(name+'/'+kind, 0)+1
        if not msg.header.frame_id.startswith(name+'/'):
            bad.add(f'{name}/{kind} header: {msg.header.frame_id}')
        if isinstance(msg, Odometry) and msg.child_frame_id != name+'/base_link':
            bad.add(f'{name} odometry child: {msg.child_frame_id}')
    def tf(msg):
        for t in msg.transforms:
            child, parent = t.child_frame_id, t.header.frame_id
            if child in ('odom', 'base_link') or parent in ('odom', 'base_link'):
                bad.add(f'unprefixed TF: {parent} -> {child}')
            if child in parents and parents[child] != parent:
                bad.add(f'multiple parents for {child}')
            parents[child] = parent
    node.create_subscription(TFMessage, '/tf', tf, 100)
    node.create_subscription(TFMessage, '/tf_static', tf,
                             QoSProfile(depth=100, durability=DurabilityPolicy.TRANSIENT_LOCAL))
    for name in a.robots:
        for kind, type_, topic in [('scan', LaserScan, 'sensors/lidar3d_0/scan'),
                                   ('imu', Imu, 'sensors/imu_0/data'),
                                   ('odom', Odometry, 'platform/odom/filtered')]:
            node.create_subscription(type_, '/'+name+'/'+topic,
                lambda msg, n=name, k=kind: record(n, k, msg), qos_profile_sensor_data)
    def fleet(msg):
        if msg.name == 'HuskyA200':
            fleet_robots.update(r.name for r in msg.robots)
    node.create_subscription(FleetState, '/fleet_states', fleet, 10)
    deadline = time.monotonic()+a.duration
    while rclpy.ok() and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    for name in a.robots:
        for kind in ('scan', 'imu', 'odom'):
            if counts.get(name+'/'+kind, 0) < 2:
                bad.add(f'Missing/stalled {name}/{kind}')
        try:
            transform = buffer.lookup_transform('map', name+'/base_link', Time())
            age = (node.get_clock().now()-Time.from_msg(transform.header.stamp)).nanoseconds/1e9
            if not -0.5 <= age <= 2.0:
                bad.add(f'Stale map -> {name}/base_link: {age:.3f}s')
        except TransformException:
            bad.add(f'Missing map -> {name}/base_link')
        if not node.get_subscriptions_info_by_topic('/'+name+'/cmd_vel'):
            bad.add(f'No controller subscribed to /{name}/cmd_vel')
    if a.require_rmf and fleet_robots != set(a.robots):
        bad.add(f'RMF participants differ: expected {sorted(a.robots)}, got {sorted(fleet_robots)}')
    print(json.dumps({'received': received, 'message_counts': counts,
                      'fleet_robots': sorted(fleet_robots), 'errors': sorted(bad)}, indent=2))
    node.destroy_node()
    rclpy.shutdown()
    raise SystemExit(1 if bad else 0)
