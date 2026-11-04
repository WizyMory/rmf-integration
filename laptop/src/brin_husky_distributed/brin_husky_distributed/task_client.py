"""Wall-time laptop task console: targeted robot requests or native RMF bidding."""
import argparse
import json
import math
import os
from pathlib import Path
import select
import shlex
import sys
import time
import uuid

from ament_index_python.packages import get_package_share_directory
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rmf_fleet_msgs.msg import FleetState
from rmf_task_msgs.msg import ApiRequest, ApiResponse, DispatchState, DispatchStates
from std_msgs.msg import String
import yaml

from .profile_info import profile_info


def parse_options(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--robot', metavar='NAME', help='Target a configured robot, e.g. devi or husky_0')
    mode.add_argument('--bid', action='store_true', help='Let the native dispatcher/fleet planners allocate the task')
    mode.add_argument('--cancel', metavar='TASK_ID', help='Cancel an allocated task by booking ID')
    mode.add_argument('--interactive', action='store_true', help='Keep a menu open in this terminal')
    mode.add_argument('--list-waypoints', action='store_true', help='List graph waypoints without contacting ROS')
    parser.add_argument('--places', nargs='+', metavar='WAYPOINT')
    parser.add_argument('--rounds', type=int, default=1)
    parser.add_argument('--traffic-profile', default='gedungWS_0')
    parser.add_argument('--timeout', type=float, default=30., help='Total request/allocation timeout in seconds')
    parser.add_argument('--dry-run', action='store_true', help='Print payload only; no ROS context or publisher')
    options = parser.parse_args(arguments)
    if options.robot is not None and not options.robot.strip():
        parser.error('--robot requires a nonempty robot name')
    if options.rounds < 1:
        parser.error('--rounds must be positive')
    if not math.isfinite(options.timeout) or not 1 <= options.timeout <= 120:
        parser.error('--timeout must be between 1 and 120 seconds')
    if not any((options.robot, options.bid, options.cancel, options.interactive, options.list_waypoints)):
        if options.places or options.dry_run:
            parser.error('Select --robot NAME or --bid explicitly')
        options.interactive = True
    if (options.robot or options.bid) and not options.places:
        parser.error('--places is required for a robot request or bidding')
    if options.places and not (options.robot or options.bid):
        parser.error('--places requires --robot NAME or --bid')
    if options.dry_run and (options.interactive or options.list_waypoints):
        parser.error('--dry-run requires --robot, --bid, or --cancel')
    if options.cancel is not None and not options.cancel.strip():
        parser.error('--cancel requires a nonempty booking ID')
    if not (options.robot or options.bid or options.interactive) and options.rounds != 1:
        parser.error('--rounds only applies to patrol tasks')
    return options


def load_targets(path=None):
    if path is None:
        path = Path(get_package_share_directory('brin_husky_distributed'))/'config/task_targets.yaml'
    document = yaml.safe_load(Path(path).read_text())
    targets = document.get('robots') if isinstance(document, dict) else None
    if (not isinstance(targets, dict) or not targets
            or not all(isinstance(k, str) and k.strip() and isinstance(v, str) and v.strip()
                       for k, v in targets.items())):
        raise ValueError('task_targets.yaml requires nonempty robot: fleet entries')
    return targets


def waypoint_rows(profile):
    rows = {}
    for level, places in profile['places'].items():
        for name, xy in places.items():
            if name in rows:
                raise ValueError('Ambiguous waypoint name on multiple levels: ' + name)
            rows[name] = (level, xy)
    if not rows:
        raise ValueError('Selected profile contains no named waypoints')
    return rows


def make_payload(targets, places=None, robot=None, bid=False, cancel=None, rounds=1, now_ns=None):
    if cancel is not None:
        if not cancel.strip() or robot or bid or places:
            raise ValueError('Cancellation requires only a nonempty booking ID')
        return {'type': 'cancel_task_request', 'task_id': cancel,
                'labels': ['BRIN laptop task console cancellation']}
    if bool(robot) == bool(bid) or not places or rounds < 1:
        raise ValueError('Choose exactly one robot or bidding and at least one waypoint')
    if robot and robot not in targets:
        raise ValueError(f'Unknown robot {robot!r}; choose {sorted(targets)}')
    payload = {'type': 'robot_task_request' if robot else 'dispatch_task_request',
               'request': {'category': 'patrol',
                           'description': {'places': list(places), 'rounds': rounds},
                           'unix_millis_earliest_start_time':
                               (time.time_ns() if now_ns is None else now_ns)//1_000_000}}
    if robot:
        payload.update(fleet=targets[robot], robot=robot)
    return payload


def validate_places(places, rows):
    invalid = [name for name in places if name not in rows]
    if invalid:
        raise ValueError(f'Unknown waypoint(s): {invalid}; use --list-waypoints')


def booking_id(response):
    state = response.get('state')
    booking = state.get('booking') if isinstance(state, dict) else None
    value = booking.get('id') if isinstance(booking, dict) else None
    return value if isinstance(value, str) and value.strip() else None


def dispatch_result(message):
    if message.status == DispatchState.STATUS_DISPATCHED:
        if (not message.assignment.is_assigned or not message.assignment.fleet_name
                or not message.assignment.expected_robot_name):
            return {'success': False, 'dispatch_status': 'invalid_assignment',
                    'errors': ['Dispatcher reported dispatch without a robot assignment']}
        return {'success': True, 'dispatch_status': 'dispatched',
                'fleet': message.assignment.fleet_name,
                'robot': message.assignment.expected_robot_name}
    if message.status in (DispatchState.STATUS_FAILED_TO_ASSIGN,
                          DispatchState.STATUS_CANCELED_IN_FLIGHT):
        return {'success': False, 'dispatch_status': 'failed_or_canceled',
                'errors': list(message.errors)}
    return None


class TaskClient(Node):
    def __init__(self, profile, targets):
        super().__init__('brin_rmf_task_client', parameter_overrides=[
            rclpy.Parameter('use_sim_time', value=False)])
        if self.get_parameter('use_sim_time').value:
            raise ValueError('The physical task console requires real time')
        self.profile, self.targets = profile, targets
        self.responses, self.dispatches, self.fleets = {}, {}, {}
        self.profile_digest, self.profile_seen_at = None, 0.
        qos = QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                         reliability=ReliabilityPolicy.RELIABLE)
        self.request_qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                                     reliability=ReliabilityPolicy.RELIABLE)
        self.request_publisher = None
        self.response_subscription = self.create_subscription(
            ApiResponse, '/task_api_responses', self.receive_response, qos)
        self.profile_subscription = self.create_subscription(
            String, '/brin_hardware/profile_digest', self.receive_profile, qos)
        self.fleet_subscription = self.create_subscription(
            FleetState, '/fleet_states', self.receive_fleet, 10)
        self.dispatch_subscription = self.create_subscription(
            DispatchStates, '/dispatch_states', self.receive_dispatch, 10)
        self.pending_id = None

    def receive_response(self, message):
        if message.request_id != self.pending_id or message.type != ApiResponse.TYPE_RESPONDING:
            return
        try:
            response = json.loads(message.json_msg)
            if not isinstance(response, dict) or type(response.get('success')) is not bool:
                raise ValueError('Expected JSON object with boolean success')
            self.responses.setdefault(message.request_id, response)
        except (ValueError, TypeError) as exc:
            self.responses.setdefault(message.request_id, {'success': False, 'errors': [str(exc)]})

    def receive_profile(self, message):
        self.profile_digest, self.profile_seen_at = message.data, time.monotonic()

    def receive_fleet(self, message):
        self.fleets[message.name] = (time.monotonic(), {r.name for r in message.robots})

    def receive_dispatch(self, message):
        self.dispatches = {state.task_id: state for state in [*message.active, *message.finished]}

    def readiness_error(self, payload):
        if self.request_publisher is None or not self.request_publisher.get_subscription_count():
            return 'RMF task API has no request subscriber'
        if payload['type'] == 'cancel_task_request':
            return None
        age = time.monotonic() - self.profile_seen_at
        if self.profile_digest != self.profile['digest'] or age > 5.:
            return 'Laptop core profile absent, stale, or different from --traffic-profile'
        active = {(fleet, robot) for fleet, (seen, names) in self.fleets.items()
                  if time.monotonic() - seen <= 5. for robot in names}
        if payload['type'] == 'robot_task_request':
            if (payload['fleet'], payload['robot']) not in active:
                return 'Target robot is not present in a recent /fleet_states message'
        elif not active:
            return 'No registered robot appears in recent /fleet_states messages'
        return None

    def transact(self, payload, timeout):
        self.request_publisher = self.create_publisher(
            ApiRequest, '/task_api_requests', self.request_qos)
        try:
            return self._transact(payload, timeout)
        finally:
            # A persistent menu must not replay old transient-local commands
            # when an adapter restarts. Retain each request only while waiting
            # for its response/allocation, then destroy that publisher/history.
            self.destroy_publisher(self.request_publisher)
            self.request_publisher = None

    def _transact(self, payload, timeout):
        request_id = 'brin_task_' + str(uuid.uuid4())
        self.pending_id = request_id
        self.responses.clear()
        deadline = time.monotonic() + timeout
        error = self.readiness_error(payload)
        while error and rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            error = self.readiness_error(payload)
        if error:
            raise RuntimeError(error + '; no request was published')
        if not rclpy.ok():
            raise RuntimeError('ROS context stopped; no request was published')
        print(json.dumps({'request_id': request_id, 'payload': payload}, indent=2), flush=True)
        # Publish once: a timeout must not create an automatic duplicate task.
        self.request_publisher.publish(ApiRequest(request_id=request_id, json_msg=json.dumps(payload)))
        while request_id not in self.responses and rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
        if request_id not in self.responses:
            raise RuntimeError(f'Response timeout; request_id={request_id}. '
                               'Task outcome is unknown; inspect RMF before retrying')
        response = self.responses[request_id]
        result = {'request_id': request_id, 'api_response': response,
                  'task_id': payload.get('task_id') or booking_id(response), 'task_completed': False}
        if not response['success']:
            return result, 1
        if payload['type'] != 'cancel_task_request' and not result['task_id']:
            raise RuntimeError('RMF response omitted booking ID; inspect state before retrying')
        if payload['type'] == 'dispatch_task_request':
            allocation = None
            while rclpy.ok() and time.monotonic() < deadline:
                state = self.dispatches.get(result['task_id'])
                allocation = dispatch_result(state) if state is not None else None
                if allocation is not None:
                    break
                rclpy.spin_once(self, timeout_sec=0.1)
            result['allocation'] = allocation
            if allocation is None:
                result['assignment_pending'] = True
                return result, 2
            return result, 0 if allocation['success'] else 1
        return result, 0


def prompt(node, label):
    print(label, end='', flush=True)
    while rclpy.ok():
        rclpy.spin_once(node, timeout_sec=0.1)
        if select.select([sys.stdin], [], [], 0)[0]:
            line = sys.stdin.readline()
            if not line:
                raise EOFError
            return line.strip()
    raise EOFError


def print_waypoints(rows):
    for number, (name, (level, xy)) in enumerate(sorted(rows.items()), 1):
        print(f'{number:>3}. {name:<20} {level}: ({xy[0]:.2f}, {xy[1]:.2f})')


def interactive(node, options, rows):
    print('BRIN RMF task console. Robot modes: ' + ', '.join(sorted(node.targets)) + ', bid')
    print('Enter q to exit; cancel to cancel an allocated booking ID.')
    while rclpy.ok():
        try:
            mode = prompt(node, '\nRobot name / bid / cancel / q: ')
            if mode == 'q':
                return 0
            if mode == 'cancel':
                task_id = prompt(node, 'Booking/task ID: ')
                payload = make_payload(node.targets, cancel=task_id)
            else:
                if mode not in node.targets and mode != 'bid':
                    print('Choose a configured robot or bid.')
                    continue
                print_waypoints(rows)
                selection = shlex.split(prompt(node, 'Waypoint name(s) or list number(s), separated by spaces: '))
                names = sorted(rows)
                places = [names[int(value)-1] if value.isdecimal()
                          and 1 <= int(value) <= len(names) else value for value in selection]
                validate_places(places, rows)
                payload = make_payload(node.targets, places=places,
                    robot=None if mode == 'bid' else mode, bid=mode == 'bid', rounds=options.rounds)
            print(json.dumps(payload, indent=2))
            if prompt(node, 'Send this RMF request? [y/N]: ').lower() != 'y':
                print('No request sent.')
                continue
            result, code = node.transact(payload, options.timeout)
            print(json.dumps(result, indent=2))
            print(f'Request result code: {code}; physical completion must be checked separately.')
        except (ValueError, RuntimeError) as exc:
            print(str(exc), file=sys.stderr)


def main(args=None):
    argv = sys.argv if args is None else [sys.argv[0], *args]
    options = parse_options(rclpy.utilities.remove_ros_args(argv)[1:])
    try:
        profile = ({'name': None, 'digest': None} if options.cancel
                   else profile_info(options.traffic_profile))
        rows, targets = ({}, {}) if options.cancel else (waypoint_rows(profile), load_targets())
        if options.list_waypoints:
            print_waypoints(rows)
            return 0
        if options.places:
            validate_places(options.places, rows)
        payload = None if options.interactive else make_payload(targets,
            places=options.places, robot=options.robot, bid=options.bid,
            cancel=options.cancel, rounds=options.rounds)
        if options.dry_run:
            print(json.dumps({'traffic_profile': profile['name'], 'profile_digest': profile['digest'],
                              'payload': payload, 'request_published': False}, indent=2))
            return 0
        if options.interactive and not sys.stdin.isatty():
            raise ValueError('Interactive mode requires a terminal; use --robot or --bid with --places')
        if os.environ.get('ROS_DOMAIN_ID') != '0':
            raise ValueError('Physical RMF task client requires domain 0; use tools/integration.bash laptop task')
        rclpy.init(args=argv)
        node = None
        try:
            node = TaskClient(profile, targets)
            if options.interactive:
                return interactive(node, options, rows)
            result, code = node.transact(payload, options.timeout)
            print(json.dumps(result, indent=2), flush=True)
            return code
        finally:
            if node is not None:
                node.destroy_node()
            rclpy.try_shutdown()
    except (EOFError, KeyboardInterrupt):
        return 130
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
