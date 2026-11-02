"""Humble RobotCommandHandle fleet using aligned TF and independent Nav2 actions."""
from datetime import timedelta
import math
from pathlib import Path
import time
import yaml
import rclpy
from rclpy.node import Node
from rclpy.time import Time
from tf2_ros import Buffer, TransformListener, TransformException
from lifecycle_msgs.srv import GetState
from lifecycle_msgs.msg import State
from rmf_fleet_msgs.msg import FleetState
import rmf_adapter as rmf
from rmf_adapter import battery, geometry, graph, plan, vehicletraits as traits
from .command import Nav2Command
from .web import add_fleet


class FleetNode(Node):
    command_type = Nav2Command
    def __init__(self):
        super().__init__('brin_devi_fleet_adapter')
        self.declare_parameter('fleet_config', '')
        self.declare_parameter('nav_graph', '')
        self.declare_parameter('server_uri', '')
        self.config = yaml.safe_load(Path(self.get_parameter('fleet_config').value).read_text())
        self.declare_parameter('robots', sorted(self.config['robots']))
        self.tf = Buffer()
        self.listener = TransformListener(self.tf, self)
        self.commands = {}
        self.registering = set()
        self.adapter = None
        self.lifecycle = {}
        self.lost_localization = set()
        self.fleet_state_subscription = self.create_subscription(
            FleetState, '/fleet_states', self.observe_fleet_state, 10)

    def start(self):
        c = self.config
        profile = traits.Profile(geometry.make_final_convex_circle(c['profile']['footprint']),
                                 geometry.make_final_convex_circle(c['profile']['vicinity']))
        self.traits = traits.VehicleTraits(traits.Limits(*c['limits']['linear']),
                                          traits.Limits(*c['limits']['angular']), profile)
        self.traits.differential.reversible = c['reversible']
        self.graph = graph.parse_graph(self.get_parameter('nav_graph').value, self.traits)
        for attempt in range(60):
            self.adapter = rmf.Adapter.make(c['fleet_name']+'_adapter', wait_time=timedelta(seconds=1))
            if self.adapter is not None:
                break
            self.get_logger().warning(f'Waiting for RMF schedule ({attempt+1}/60)')
            rclpy.spin_once(self, timeout_sec=0.1)
        if self.adapter is None:
            raise RuntimeError('RMF traffic schedule unavailable after 60 attempts')
        if self.get_parameter('use_sim_time').value:
            self.adapter.node.use_sim_time()
        self.adapter.start()
        self.fleet = add_fleet(self.adapter, c['fleet_name'], self.traits, self.graph,
                               self.get_parameter('server_uri').value)
        b = c['battery_system']; m = c['mechanical_system']
        battery_system = battery.BatterySystem.make(b['voltage'], b['capacity'], b['charging_current'])
        mechanical = battery.MechanicalSystem.make(m['mass'], m['moment_of_inertia'], m['friction_coefficient'])
        ok = self.fleet.set_task_planner_params(
            battery_system, battery.SimpleMotionPowerSink(battery_system, mechanical),
            battery.SimpleDevicePowerSink(battery_system, battery.PowerSystem.make(c['ambient_power'])),
            battery.SimpleDevicePowerSink(battery_system, battery.PowerSystem.make(c['tool_power'])),
            c['recharge_threshold'], c['recharge_soc'], c['account_for_battery_drain'], c['finishing_request'])
        if not ok:
            raise RuntimeError('RMF rejected task planner parameters')
        self.fleet.fleet_state_publish_period(timedelta(seconds=1))
        self.fleet.consider_patrol_requests(self.consider_patrol)
        for name in self.get_parameter('robots').value:
            if name not in c['robots'] or self.graph.find_waypoint(c['robots'][name]['charger']) is None:
                raise ValueError(f'Missing robot configuration or charger: {name}')
            self.commands[name] = self.command_type(self, name, self.adapter, c)
            self.lifecycle[name] = dict(client=self.create_client(GetState, f'/{name}/bt_navigator/get_state'),
                                        future=None, next_check=0.0)
        self.create_timer(1.0/c['update_frequency'], self.tick)

    def consider_patrol(self, description):
        confirmation = rmf.fleet_update_handle.Confirmation()
        places = description.get('places', [])
        if places and all(
            (isinstance(p, str) and self.graph.find_waypoint(p) is not None)
            or (type(p) is int and 0 <= p < self.graph.num_waypoints)
            for p in places
        ):
            confirmation.accept()
        else:
            confirmation.add_errors(['Patrol requires valid graph waypoint names or indices'])
        return confirmation

    def observe_fleet_state(self, message):
        if message.name != self.config['fleet_name']:
            return
        for robot in message.robots:
            command = self.commands.get(robot.name)
            if command is not None:
                command.observe_task(robot.task_id)

    def distance_to_waypoint(self, waypoint, pose):
        target = self.graph.get_waypoint(waypoint).location
        return math.hypot(float(target[0])-pose[0], float(target[1])-pose[1])

    def pose_in_frame(self, name, frame):
        transform = self.tf.lookup_transform(frame, name+'/base_link', Time())
        age = (self.get_clock().now()-Time.from_msg(transform.header.stamp)).nanoseconds/1e9
        if age > self.config['tf_max_age'] or age < -0.5:
            raise RuntimeError(f'Stale TF for {name} in {frame}: {age:.2f}s')
        t, q = transform.transform.translation, transform.transform.rotation
        return [t.x, t.y, math.atan2(2*(q.w*q.z+q.x*q.y),
                                    1-2*(q.y*q.y+q.z*q.z))]

    def tick(self):
        c = self.config
        for name, command in self.commands.items():
            state = self.lifecycle[name]
            if state['future'] is not None and state['future'].done():
                try:
                    command.navigation_ready = state['future'].result().current_state.id == State.PRIMARY_STATE_ACTIVE
                except Exception:
                    command.navigation_ready = False
                state['future'] = None
            if time.monotonic() >= state['next_check'] and state['future'] is None and state['client'].service_is_ready():
                state['future'] = state['client'].call_async(GetState.Request())
                state['next_check'] = time.monotonic()+1.0
            try:
                pose = self.pose_in_frame(name, 'map')
                command.pose = pose
                if name in self.lost_localization and command.update:
                    self.lost_localization.discard(name)
                    command.update.replan()
            except (TransformException, RuntimeError):
                if command.pose is not None:
                    command.pose = None
                    command.stop()
                    self.lost_localization.add(name)
                    self.get_logger().error(f'{name}: localization lost; canceling navigation')
                command.tick()
                continue
            starts = plan.compute_plan_starts(self.graph, c['map_name'], pose, self.adapter.now(),
                                             c['max_merge_waypoint_distance'], c['max_merge_lane_distance'])
            if starts:
                command.last_graph_waypoint = min(
                    starts, key=lambda start: self.distance_to_waypoint(
                        start.waypoint, pose)).waypoint
                if command.task_id is not None and command.origin_waypoint is None:
                    command.origin_waypoint = (
                        command.first_path_origin
                        if command.first_path_origin is not None
                        else command.last_graph_waypoint)
            if command.update is None and name not in self.registering:
                if starts and command.client.server_is_ready() and command.navigation_ready:
                    self.registering.add(name)
                    self.fleet.add_robot(command, name, self.traits.profile, starts,
                                         lambda update, n=name: self.registered(n, update))
            elif command.update is not None:
                if starts:
                    command.update.update_position(starts)
                else:
                    # A free-space Nav2 path may temporarily cut an RMF graph
                    # corner or detour around an obstacle. While an RMF path
                    # target is known, report the actual TF pose as off-grid
                    # and allow Nav2 to merge back into that target instead of
                    # canceling the goal and creating a 5 Hz replan loop.
                    target_waypoint = command.next_graph_waypoint()
                    if target_waypoint is not None:
                        command.update.update_off_grid_position(pose, target_waypoint)
                    else:
                        command.update.update_lost_position(c['map_name'], pose,
                            c['max_merge_waypoint_distance'], c['max_merge_lane_distance'])
                command.update.update_battery_soc(c['initial_battery_soc'])
            command.tick()

    def registered(self, name, update):
        command = self.commands[name]
        command.update = update
        update.set_charger_waypoint(self.graph.find_waypoint(self.config['robots'][name]['charger']).index)
        update.update_battery_soc(self.config['initial_battery_soc'])
        self.get_logger().info(f'Registered {name} in {self.config["fleet_name"]}')


def main(args=None):
    rclpy.init(args=args)
    rmf.init_rclcpp()
    node = FleetNode()
    try:
        node.start()
        rclpy.spin(node)
    finally:
        for command in node.commands.values():
            command.shutdown()
        # Give asynchronous cancellation a bounded opportunity to reach Nav2.
        deadline = time.monotonic()+2.0
        while (rclpy.ok() and time.monotonic() < deadline
               and any(c.goal or c.backup_goal for c in node.commands.values())):
            rclpy.spin_once(node, timeout_sec=0.1)
        if node.adapter:
            node.adapter.stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
