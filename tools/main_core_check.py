#!/usr/bin/env python3
"""Read-only RMF core discovery, profile/map health and duplicate-core guard."""
import argparse
from collections import Counter
import json
import os
import time


CORE_NAMES = ('rmf_traffic_schedule_primary', 'rmf_task_dispatcher',
              'building_map_server', 'brin_hardware_profile_announcer')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--require-absent', action='store_true')
    mode.add_argument('--status', action='store_true')
    parser.add_argument('--traffic-profile', default='gedungWS_0')
    parser.add_argument('--timeout', type=float, default=5.0)
    args = parser.parse_args()
    if not 1.0 <= args.timeout <= 20.0:
        parser.error('timeout must be between 1 and 20 seconds')
    if os.environ.get('ROS_DOMAIN_ID', '0') != '0':
        parser.error('the physical RMF integration uses domain 0')

    import rclpy
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    from rmf_building_map_msgs.msg import BuildingMap
    from rmf_fleet_msgs.msg import FleetState
    from std_msgs.msg import String

    from brin_husky_distributed.profiles import resolve_profile

    expected_digest = resolve_profile(args.traffic_profile)['digest']
    rclpy.init()
    node = rclpy.create_node('rmf_main_status_' + str(os.getpid()))
    digests, maps, fleets = set(), {}, {}
    qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                     durability=DurabilityPolicy.TRANSIENT_LOCAL)

    def on_map(message):
        maps[message.name] = [level.name for level in message.levels]

    def on_fleet(message):
        fleets[message.name] = [robot.name for robot in message.robots]

    try:
        node.create_subscription(String, '/brin_hardware/profile_digest', lambda m: digests.add(m.data), qos)
        node.create_subscription(BuildingMap, '/map', on_map, qos)
        node.create_subscription(FleetState, '/fleet_states', on_fleet, 10)
        deadline = time.monotonic() + args.timeout
        observed = Counter()
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            observed = Counter(name for name, namespace in node.get_node_names_and_namespaces())
        counts = {name: observed[name] for name in CORE_NAMES}
        publishers = node.count_publishers('/brin_hardware/profile_digest')
        absent = not any(counts.values()) and publishers == 0
        healthy = (all(count == 1 for count in counts.values()) and publishers == 1
                   and digests == {expected_digest} and any(maps.values()))
        print(json.dumps({
            'core_absent': absent, 'healthy': healthy, 'core_nodes': counts,
            'traffic_profile': args.traffic_profile, 'expected_digest': expected_digest,
            'received_digests': sorted(digests), 'profile_publishers': publishers,
            'building_maps': maps, 'fleets': fleets,
            'domain_id': int(os.environ.get('ROS_DOMAIN_ID', '0')),
            'rmw': os.environ.get('RMW_IMPLEMENTATION', ''),
            'tasks_sent': 0, 'goals_sent': 0,
        }, indent=2), flush=True)
        return 0 if (absent if args.require_absent else healthy) else 2
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
