"""Read-only preflight and native Humble fleet adapter, one robot per process."""
from datetime import timedelta
import fcntl
import json
import os
from pathlib import Path
import signal
import time

from .config import Alignment, distance_to_graph, environment
from .controller import Controller
from .gateway import Gateway

CORE = ('rmf_traffic_schedule_primary', 'rmf_task_dispatcher', 'building_map_server')


def report(config, state, digest, digest_age, nodes, publishers):
    errors = list(state.get('errors', ['Nav2 gateway has not reported']))
    if not state.get('nav2_ready') and not errors:
        errors.append('Nav2 is not ready')
    if digest != config['rmf']['expected_profile_digest'] or digest_age > 5 or publishers != 1:
        errors.append('Expected one fresh matching RMF profile publisher')
    for name in CORE:
        if nodes.count(name) != 1:
            errors.append('Expected exactly one core node: '+name)
    if state.get('pose') is not None:
        pose = Alignment(config['alignment']).to_rmf(state['pose'])
        if distance_to_graph(config, pose) > config['nav2']['max_graph_distance']:
            errors.append('Robot is too far from the configured RMF graph')
    return {**state, 'errors': errors, 'accepted': not errors,
            'robot': config['robot']['name'], 'fleet': config['robot']['fleet'],
            'robot_registered': False, 'goals_sent': 0}


def prepare_environment(config):
    for key, value in environment(config['rmf']).items():
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)


def observe(config, timeout=15., inspect=False):
    prepare_environment(config)
    import rclpy
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    from std_msgs.msg import String
    rclpy.init(args=[], domain_id=config['rmf']['domain_id'])
    node = rclpy.create_node('rmf_nav2_preflight_'+config['robot']['name'])
    gateway = Gateway(config)
    received = [None, 0.]
    def profile(message):
        received[:] = message.data, time.monotonic()
    qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                     reliability=ReliabilityPolicy.RELIABLE)
    subscription = node.create_subscription(String, config['rmf']['profile_topic'], profile, qos)
    try:
        deadline = time.monotonic()+timeout
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.05)
            gateway.poll()
        state = gateway.state if gateway.fresh else {'errors': ['Nav2 gateway unavailable'], 'nav2_ready': False}
        result = report(config, state, received[0], time.monotonic()-received[1],
                        node.get_node_names(), node.count_publishers(config['rmf']['profile_topic']))
        if inspect:
            result['accepted'] = False
            result['inspection_only'] = True
        print(json.dumps(result, indent=2), flush=True)
        return 0 if (state.get('nav2_ready') if inspect else result['accepted']) else 2
    finally:
        gateway.close()
        node.destroy_node()
        rclpy.try_shutdown()


def run(config):
    prepare_environment(config)
    # rclcpp/RMF reads the RMF DDS environment at its first initialization.
    import rclpy
    from rclpy.signals import SignalHandlerOptions
    from rclpy.qos import DurabilityPolicy, QoSProfile
    from rmf_fleet_msgs.msg import FleetState
    from std_msgs.msg import String
    import rmf_adapter as rmf
    from rmf_adapter import battery, geometry, graph, plan, vehicletraits as traits

    name, fleet_name = config['robot']['name'], config['robot']['fleet']
    directory = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp'))/('rmf_nav2_'+str(os.getuid()))
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = (directory/(str(config['rmf']['domain_id'])+'_'+fleet_name+'.lock')).open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise RuntimeError('This fleet already has an adapter on this computer')
    rclpy.init(args=[], domain_id=config['rmf']['domain_id'], signal_handler_options=SignalHandlerOptions.NO)
    rmf.init_rclcpp()
    node = rclpy.create_node('rmf_nav2_adapter_'+name)
    gateway, adapter, command, handle = None, None, None, None
    stopping = [False]
    previous = {s: signal.signal(s, lambda *_: stopping.__setitem__(0, True))
                for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        from .render import transit_xml
        tree = directory/(name+'_transit.xml')
        tree.write_text(transit_xml(config))
        gateway = Gateway(config, allow_commands=True)
        alignment = Alignment(config['alignment'])
        received, update, issue = [None, 0.], [None], [None]
        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        def profile(message):
            received[:] = message.data, time.monotonic()
        profile_sub = node.create_subscription(String, config['rmf']['profile_topic'], profile, qos)
        deadline = time.monotonic()+30
        while not stopping[0]:
            rclpy.spin_once(node, timeout_sec=.05)
            gateway.poll()
            ready = report(config, gateway.state if gateway.fresh else {}, received[0],
                           time.monotonic()-received[1], node.get_node_names(),
                           node.count_publishers(config['rmf']['profile_topic']))
            if ready['accepted']:
                break
            if time.monotonic() > deadline:
                raise RuntimeError('Runtime preflight failed: '+json.dumps(ready['errors']))
        if stopping[0]:
            return
        if node.get_node_names().count('rmf_nav2_adapter_'+name) != 1:
            raise RuntimeError('Duplicate adapter node detected')
        vehicle = traits.VehicleTraits(
            traits.Limits(config['motion']['linear_speed'], config['motion']['linear_acceleration']),
            traits.Limits(config['motion']['angular_speed'], config['motion']['angular_acceleration']),
            traits.Profile(geometry.make_final_convex_circle(config['geometry']['footprint_radius']),
                           geometry.make_final_convex_circle(config['geometry']['vicinity_radius'])))
        vehicle.differential.reversible = False
        nav_graph = graph.parse_graph(config['rmf']['nav_graph'], vehicle)
        if config['nav2']['final_orientation_only']:
            for index in range(nav_graph.num_lanes):
                lane = nav_graph.get_lane(index)
                if lane.entry.orientation_constraint is not None or lane.exit.orientation_constraint is not None:
                    raise RuntimeError('Transit mode requires a graph without lane orientation constraints')
        for attempt in range(4):
            if stopping[0]:
                return
            adapter = rmf.Adapter.make(fleet_name+'_rmf_nav2', wait_time=timedelta(seconds=5))
            if adapter is not None:
                break
        if adapter is None:
            raise RuntimeError('Native RMF schedule handshake failed after 4 bounded attempts')
        adapter.start()
        uri = config['rmf'].get('web_uri', '')
        fleet = adapter.add_fleet(fleet_name, vehicle, nav_graph, uri) if uri else adapter.add_fleet(fleet_name, vehicle, nav_graph)
        # Estimates only; consumption-based planning and charger travel disabled.
        bs = battery.BatterySystem.make(24., 20., 5.)
        mechanical = battery.MechanicalSystem.make(60., 2.5, .2)
        if not fleet.set_task_planner_params(bs, battery.SimpleMotionPowerSink(bs, mechanical),
                battery.SimpleDevicePowerSink(bs, battery.PowerSystem.make(20.)),
                battery.SimpleDevicePowerSink(bs, battery.PowerSystem.make(0.)),
                .2, .95, False, 'nothing'):
            raise RuntimeError('RMF rejected planner parameters')
        fleet.fleet_state_publish_period(timedelta(seconds=1))
        def consider(description):
            confirmation = rmf.fleet_update_handle.Confirmation()
            places = description.get('places', [])
            if places and all(isinstance(p, str) and nav_graph.find_waypoint(p) is not None for p in places):
                confirmation.accept()
            else:
                confirmation.add_errors(['Only patrol between configured named waypoints is supported'])
            return confirmation
        fleet.consider_patrol_requests(consider)
        def failure(reason):
            node.get_logger().error(reason)
            if update[0] is not None and issue[0] is None:
                issue[0] = update[0].create_issue(rmf.robot_update_handle.Tier.Error,
                                                'navigation', {'detail': reason})
        def recovered():
            if issue[0] is not None:
                issue[0].resolve({'detail': 'Navigation path completed successfully'})
                issue[0] = None
        command = Controller(config, gateway, alignment, adapter.now, node.get_logger().info,
                             failure, lambda: update[0].replan() if update[0] is not None else None,
                             str(tree), recovered)
        class Handle(rmf.RobotCommandHandle):
            def __init__(self):
                super().__init__()
            def follow_new_path(self, waypoints, estimator, finished):
                command.follow(waypoints, estimator, finished)
            def stop(self):
                command.stop()
            def dock(self, dock_name, finished):
                command.dock(dock_name)
        handle = Handle()
        def task(message):
            if message.name == fleet_name:
                for robot in message.robots:
                    if robot.name == name:
                        command.task(robot.task_id)
        state_sub = node.create_subscription(FleetState, '/fleet_states', task, 10)
        registering = False
        def registered(robot_update):
            robot_update.enable_responsive_wait(False)
            robot_update.set_charger_waypoint(nav_graph.find_waypoint(config['rmf']['home_waypoint']).index)
            update[0] = robot_update
            node.get_logger().info('Registered '+name+' in '+fleet_name)
        while not stopping[0] and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=1/config['nav2']['update_hz'])
            events = gateway.poll()
            state = gateway.state if gateway.fresh else {}
            # Graph proximity is needed for initial registration. Off-grid
            # motion while following a known path is reported by actual pose.
            health = report(config, state, received[0], time.monotonic()-received[1],
                            node.get_node_names(), node.count_publishers(config['rmf']['profile_topic']))
            healthy = not any(e != 'Robot is too far from the configured RMF graph' for e in health['errors'])
            if healthy and state.get('pose') is not None:
                pose = alignment.to_rmf(state['pose'])
                starts = plan.compute_plan_starts(nav_graph, config['rmf']['level'], pose, adapter.now(),
                                                  .2, config['nav2']['max_graph_distance'])
                if update[0] is None and not registering and starts and health['accepted']:
                    registering = True
                    fleet.add_robot(handle, name, vehicle.profile, starts, registered)
                elif update[0] is not None:
                    if starts:
                        update[0].update_position(starts)
                    elif command.next_graph_waypoint() is not None:
                        update[0].update_off_grid_position(pose, command.next_graph_waypoint())
                    else:
                        update[0].update_lost_position(config['rmf']['level'], pose, .2,
                                                      config['nav2']['max_graph_distance'])
                    if state.get('battery_soc') is not None:
                        update[0].update_battery_soc(state['battery_soc'])
            command.acknowledge(events)
            command.tick(state, events, healthy and update[0] is not None)
    finally:
        if command is not None and gateway is not None:
            try:
                command.cancel()
            except (BrokenPipeError, OSError):
                pass
        if gateway is not None:
            gateway.close()
        if adapter is not None:
            adapter.stop()
        node.destroy_node()
        rclpy.try_shutdown()
        for number, handler in previous.items():
            signal.signal(number, handler)
        lock.close()
