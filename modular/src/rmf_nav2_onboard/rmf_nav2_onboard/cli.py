"""Onboard robot onboarding, preflight, adapter and core-side commands."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
import tarfile
import time
import uuid

import yaml

from .config import ConfigError, asset_hashes, load, site_digest


def options(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('new', help='Create an uncommissioned robot profile')
    create.add_argument('--name', required=True)
    create.add_argument('--fleet', required=True)
    create.add_argument('--namespace', default='')
    create.add_argument('--robot-domain', type=int, default=0)
    create.add_argument('--rmf-domain', type=int, default=0)
    create.add_argument('--output', type=Path, required=True)
    for command in ('validate', 'pin-assets', 'waypoints', 'inspect', 'preflight', 'run',
                    'task', 'render-nav2', 'render-service', 'publish-profile', 'core'):
        sub = commands.add_parser(command)
        sub.add_argument('--config', type=Path, required=True)
        if command == 'validate':
            sub.add_argument('--commissioned', action='store_true')
        if command in ('inspect', 'preflight', 'task'):
            sub.add_argument('--timeout', type=float, default=15.)
        if command == 'run':
            sub.add_argument('--enable-dispatch', action='store_true')
        if command == 'task':
            mode = sub.add_mutually_exclusive_group(required=True)
            mode.add_argument('--places', nargs='+')
            mode.add_argument('--cancel', metavar='TASK_ID')
            sub.add_argument('--rounds', type=int, default=1)
            sub.add_argument('--send', action='store_true', help='Publish once; default prints a dry-run payload')
        if command in ('render-nav2', 'render-service'):
            sub.add_argument('--output', type=Path, required=True)
        if command == 'render-service':
            sub.add_argument('--workspace', type=Path, required=True)
            sub.add_argument('--underlay', default='')
    bundle = commands.add_parser('bundle', help='Export reusable source only, without robot site profiles/build/log')
    bundle.add_argument('--output', type=Path, required=True)
    return parser.parse_args(argv)


def create_profile(args):
    for value in (args.name, args.fleet):
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', value):
            raise ConfigError('name and fleet must be ROS identifiers')
    namespace = args.namespace.rstrip('/')
    if namespace and not re.fullmatch(r'/[A-Za-z][A-Za-z0-9_/]*', namespace):
        raise ConfigError('namespace must be empty, /, or /robot_namespace')
    if not 0 <= args.robot_domain <= 232 or not 0 <= args.rmf_domain <= 232:
        raise ConfigError('ROS domains must be 0..232')
    source = (Path(__file__).parent/'templates/robot.yaml').read_text()
    source = source.replace('__ROBOT__', args.name).replace('__FLEET__', args.fleet).replace('__NS__', namespace)
    config = yaml.safe_load(source)
    config['nav2']['domain_id'], config['rmf']['domain_id'] = args.robot_domain, args.rmf_domain
    # Preserve template comments when default domains apply.
    if args.robot_domain or args.rmf_domain:
        source = yaml.safe_dump(config, sort_keys=False)
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output/'robot.yaml'
    with target.open('x') as stream:
        stream.write(source)
    (args.output/'assets').mkdir(exist_ok=True)
    print('Created '+str(target)+'. Fill measured parameters and copy canonical site assets before validation.')
    return 0


def task_payload(config, args):
    if args.rounds < 1:
        raise ConfigError('rounds must be positive')
    if args.cancel:
        if not args.cancel.strip():
            raise ConfigError('task ID must not be blank')
        return {'type': 'cancel_task_request', 'task_id': args.cancel,
                'labels': ['rmf_nav2_onboard operator cancellation']}
    names = {v[2].get('name') for v in config['_vertices'] if len(v)>2}
    if not args.places or any(p not in names for p in args.places):
        raise ConfigError('Unknown waypoint; use waypoints --config robot.yaml')
    return {'type': 'robot_task_request', 'fleet': config['robot']['fleet'],
            'robot': config['robot']['name'], 'request': {'category': 'patrol',
            'description': {'places': args.places, 'rounds': args.rounds},
            'unix_millis_earliest_start_time': time.time_ns()//1_000_000}}


def send_task(config, payload, timeout):
    from .runtime import prepare_environment
    prepare_environment(config)
    import rclpy
    from rmf_fleet_msgs.msg import FleetState
    from rmf_task_msgs.msg import ApiRequest, ApiResponse
    from std_msgs.msg import String
    from rclpy.qos import QoSProfile, DurabilityPolicy
    rclpy.init(args=[], domain_id=config['rmf']['domain_id'])
    node = rclpy.create_node('rmf_nav2_task_'+uuid.uuid4().hex[:10])
    qos = QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    response, fleet_seen, profile = {}, [0.], [None, 0.]
    request_id = 'modular_'+str(uuid.uuid4())
    def answered(message):
        if message.request_id == request_id:
            response.update(json.loads(message.json_msg))
    def fleet(message):
        if message.name == config['robot']['fleet'] and any(r.name == config['robot']['name'] for r in message.robots):
            fleet_seen[0] = time.monotonic()
    def digest(message):
        profile[:] = message.data, time.monotonic()
    subscriptions = [node.create_subscription(ApiResponse, '/task_api_responses', answered, qos),
                     node.create_subscription(FleetState, '/fleet_states', fleet, 10),
                     node.create_subscription(String, config['rmf']['profile_topic'], digest,
                         QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))]
    publisher = node.create_publisher(ApiRequest, '/task_api_requests', qos)
    try:
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.05)
            ready = publisher.get_subscription_count() > 0
            if payload['type'] != 'cancel_task_request':
                ready = (ready and time.monotonic()-fleet_seen[0] < 5
                         and profile[0] == config['rmf']['expected_profile_digest']
                         and time.monotonic()-profile[1] < 5)
            if ready:
                break
        else:
            raise RuntimeError('Task API/registered robot/profile not ready; no request was published')
        publisher.publish(ApiRequest(request_id=request_id, json_msg=json.dumps(payload)))
        print(json.dumps({'request_id': request_id, 'published_once': True}, indent=2), flush=True)
        while not response and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.05)
        if not response:
            raise RuntimeError('Response timed out after one publication; check request_id before resubmitting')
        print(json.dumps(response, indent=2), flush=True)
        return 0 if response.get('success') is True else 2
    finally:
        node.destroy_publisher(publisher)  # Destroy retained command history.
        node.destroy_node()
        rclpy.try_shutdown()


def publish_profile(config):
    from .runtime import prepare_environment
    digest = site_digest(config)
    if digest != config['rmf']['expected_profile_digest']:
        raise ConfigError('Own profile publisher requires the digest computed from canonical assets; do not impersonate a BRIN publisher')
    prepare_environment(config)
    import rclpy
    from rclpy.qos import QoSProfile, DurabilityPolicy
    from std_msgs.msg import String
    rclpy.init(args=[], domain_id=config['rmf']['domain_id'])
    node = rclpy.create_node('rmf_nav2_site_profile')
    publisher = node.create_publisher(String, config['rmf']['profile_topic'],
        QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
    try:
        end = time.monotonic()+2
        while time.monotonic()<end:
            rclpy.spin_once(node, timeout_sec=.05)
        if node.count_publishers(config['rmf']['profile_topic']) != 1:
            raise RuntimeError('A profile publisher already exists; use that core profile instead')
        timer = node.create_timer(1., lambda: publisher.publish(String(data=digest)))
        print('Publishing site profile at 1 Hz; no task or motion command', flush=True)
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    return 0


def export_bundle(output):
    workspace = Path(os.environ.get('RMF_NAV2_MODULE_ROOT', Path(__file__).resolve().parents[3])).resolve()
    output = output.resolve()
    # Publish only maintained source, tests, tools and docs; profiles are opt-in Git additions.
    roots = [workspace/name for name in ('src', 'tools', 'docs', '.github', 'README.md', 'LICENSE', '.gitignore')]
    files = sorted(p for root in roots for p in ([root] if root.is_file() else root.rglob('*'))
                   if p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts
                   and not any(part.endswith('.egg-info') for part in p.parts) and p.suffix != '.pyc')
    with output.open('xb') as stream, tarfile.open(fileobj=stream, mode='w:xz') as archive:
        for file in files:
            archive.add(file, arcname='rmf-nav2-modular/'+str(file.relative_to(workspace)), recursive=False)
    print(str(output))
    return 0


def main(argv=None):
    try:
        args = options(argv)
        if args.command == 'new':
            return create_profile(args)
        if args.command == 'bundle':
            return export_bundle(args.output)
        if hasattr(args, 'timeout') and (not math.isfinite(args.timeout) or not 1 <= args.timeout <= 120):
            raise ConfigError('timeout must be between 1 and 120 seconds')
        config = load(args.config, commissioned=args.command in ('run', 'preflight') or getattr(args, 'commissioned', False),
                      pinned=args.command != 'pin-assets', require_profile=args.command != 'pin-assets')
        if args.command == 'pin-assets':
            lock = args.config.resolve().with_name('assets.lock.json')
            lock.write_text(json.dumps(asset_hashes(config), indent=2)+'\n')
            print(json.dumps({'lock_file': str(lock), 'own_core_site_digest': site_digest(config)}, indent=2))
        elif args.command == 'validate':
            print(json.dumps({'valid': True, 'robot': config['robot'], 'assets': asset_hashes(config)}, indent=2))
        elif args.command == 'waypoints':
            print(json.dumps([{'name': v[2]['name'], 'xy': v[:2]} for v in config['_vertices']
                              if len(v)>2 and v[2].get('name')], indent=2))
        elif args.command in ('inspect', 'preflight'):
            from .runtime import observe
            return observe(config, args.timeout, inspect=args.command == 'inspect')
        elif args.command == 'run':
            if not args.enable_dispatch:
                raise ConfigError('run requires --enable-dispatch after commissioning; use inspect for read-only checks')
            from .runtime import run
            run(config)
        elif args.command == 'task':
            payload = task_payload(config, args)
            if not args.send:
                print(json.dumps({'dry_run': True, 'payload': payload}, indent=2))
            else:
                return send_task(config, payload, args.timeout)
        elif args.command in ('render-nav2', 'render-service'):
            from .render import nav2_fragment, service
            text = nav2_fragment(config) if args.command == 'render-nav2' else service(config, args.workspace, args.underlay)
            with args.output.open('x') as stream:
                stream.write(text)
            print('Generated for review only: '+str(args.output))
        elif args.command == 'publish-profile':
            return publish_profile(config)
        elif args.command == 'core':
            from .runtime import prepare_environment
            prepare_environment(config)
            os.execvp('ros2', ['ros2', 'launch', 'rmf_nav2_onboard', 'core.launch.py', 'config:='+str(args.config.resolve())])
        return 0
    except (ConfigError, OSError, RuntimeError, ValueError) as exc:
        print('ERROR: '+str(exc), file=sys.stderr)
        return 2


def profile_main():
    from rclpy.utilities import remove_ros_args
    return main(['publish-profile', *remove_ros_args(sys.argv)[1:]])


if __name__ == '__main__':
    raise SystemExit(main())
