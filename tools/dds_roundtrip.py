#!/usr/bin/env python3
"""Bounded DDS transport check; publishes only isolated diagnostic Strings.

Run the same --session on laptop and robot, with their respective --role.
This is not a fleet adapter, robot-state publisher, or movement test.
"""
import argparse
import json
import re
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=('laptop', 'robot'), required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--timeout', type=float, default=20.0)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]{0,63}', args.session):
        parser.error('session must be a ROS-safe identifier, up to 64 characters')
    if not 1.0 <= args.timeout <= 60.0:
        parser.error('timeout must be between 1 and 60 seconds')

    import rclpy
    from std_msgs.msg import String

    rclpy.init(args=[])
    node = rclpy.create_node('rmf_link_check_' + args.role)
    base = '/brin_link_check/' + args.session
    received = set()
    sent = set()
    publisher = node.create_publisher(
        String, base + ('/request' if args.role == 'laptop' else '/reply'), 10)

    def receive(message):
        try:
            data = json.loads(message.data)
        except (ValueError, TypeError):
            return
        if not isinstance(data, dict) or data.get('session') != args.session:
            return
        sequence = data.get('sequence')
        if type(sequence) is not int or sequence < 0:
            return
        if args.role == 'robot':
            received.add(sequence)
            publisher.publish(message)
            sent.add(sequence)
        elif sequence in sent:
            received.add(sequence)

    node.create_subscription(
        String, base + ('/reply' if args.role == 'laptop' else '/request'),
        receive, 10)
    started = time.monotonic()
    sequence = 0
    next_send = started
    try:
        while time.monotonic() - started < args.timeout:
            now = time.monotonic()
            if args.role == 'laptop' and now >= next_send:
                sent.add(sequence)
                publisher.publish(String(data=json.dumps(
                    {'session': args.session, 'sequence': sequence})))
                sequence += 1
                next_send = now + 0.25
            rclpy.spin_once(node, timeout_sec=0.1)
            if args.role == 'laptop' and len(received) >= 3:
                break
        result = {
            'role': args.role, 'session': args.session,
            'sent_unique': len(sent), 'received_unique': len(received),
            'passed': len(received) >= 3,
            'elapsed_seconds': round(time.monotonic() - started, 2),
            'goals_sent': 0,
        }
        print(json.dumps(result), flush=True)
        return 0 if result['passed'] else 2
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
