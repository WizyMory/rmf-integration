"""Use the proven RMF command lifecycle with a physical Nav2 server."""
from datetime import timedelta
import time

from lifecycle_msgs.srv import GetState
import rclpy
import rmf_adapter as rmf
from rmf_adapter import battery, geometry, graph, vehicletraits as traits

from brin_husky_fleet_adapter.adapter import FleetNode
from brin_husky_fleet_adapter.command import Nav2Command
from brin_husky_fleet_adapter.web import add_fleet


class HardwareCommand(Nav2Command):
    def __init__(self, node, name, adapter, config):
        super().__init__(node, name, adapter, config)
        # Nav2 opens a behavior-tree path on the robot computer. An empty path
        # selects its installed default rather than a path on the RMF server.
        self.behavior_tree = ''

    def follow_new_path(self, waypoints, next_arrival_estimator, path_finished_callback):
        # Registration may enqueue an idle path before responsive wait is disabled.
        # Discard it without reporting a physical arrival that did not occur.
        if self.task_id is None:
            self.node.get_logger().warning(
                f'{self.name}: blocked RMF path without an active task ID')
            return
        super().follow_new_path(waypoints, next_arrival_estimator, path_finished_callback)

    def observe_task(self, task_id):
        previous_task = self.task_id
        super().observe_task(task_id)
        if self.task_id != previous_task:
            # Drop paths from the preceding task before asking for a fresh path.
            # This also recovers task paths received before /fleet_states named the task.
            self.stop()
            if self.task_id is not None and self.update is not None:
                self.update.replan()

    def _start_escape(self):
        # The simulation recovery includes an autonomous reverse maneuver.
        # Its rear sensing/clearance has not been accepted on the real Husky.
        self._recovery_failed('Physical Husky: operator intervention required; '
                              'automatic BackUp is disabled')


class HardwareFleetNode(FleetNode):
    def registered(self, name, update):
        update.enable_responsive_wait(False)
        super().registered(name, update)
        self.get_logger().info(
            f'{name}: responsive wait disabled; Nav2 paths require an active RMF task ID')

    def start(self):
        if self.get_parameter('use_sim_time').value:
            raise ValueError('Physical Husky adapter requires use_sim_time:=false')
        names = list(self.get_parameter('robots').value)
        if names != ['husky_0']:
            raise ValueError('This physical milestone enables only husky_0')
        c = self.config
        profile = traits.Profile(
            geometry.make_final_convex_circle(c['profile']['footprint']),
            geometry.make_final_convex_circle(c['profile']['vicinity']))
        self.traits = traits.VehicleTraits(
            traits.Limits(*c['limits']['linear']),
            traits.Limits(*c['limits']['angular']), profile)
        self.traits.differential.reversible = c['reversible']
        self.graph = graph.parse_graph(self.get_parameter('nav_graph').value, self.traits)
        for attempt in range(60):
            self.adapter = rmf.Adapter.make(
                c['fleet_name'] + '_hardware_adapter',
                wait_time=timedelta(seconds=1))
            if self.adapter is not None:
                break
            self.get_logger().warning(f'Waiting for RMF schedule ({attempt + 1}/60)')
            rclpy.spin_once(self, timeout_sec=0.1)
        if self.adapter is None:
            raise RuntimeError('RMF traffic schedule unavailable after 60 attempts')
        self.adapter.start()
        self.fleet = add_fleet(
            self.adapter, c['fleet_name'], self.traits, self.graph,
            self.get_parameter('server_uri').value)
        b, m = c['battery_system'], c['mechanical_system']
        battery_system = battery.BatterySystem.make(
            b['voltage'], b['capacity'], b['charging_current'])
        mechanical = battery.MechanicalSystem.make(
            m['mass'], m['moment_of_inertia'], m['friction_coefficient'])
        if not self.fleet.set_task_planner_params(
                battery_system,
                battery.SimpleMotionPowerSink(battery_system, mechanical),
                battery.SimpleDevicePowerSink(
                    battery_system, battery.PowerSystem.make(c['ambient_power'])),
                battery.SimpleDevicePowerSink(
                    battery_system, battery.PowerSystem.make(c['tool_power'])),
                c['recharge_threshold'], c['recharge_soc'],
                c['account_for_battery_drain'], c['finishing_request']):
            raise RuntimeError('RMF rejected task planner parameters')
        self.fleet.fleet_state_publish_period(timedelta(seconds=1))
        self.fleet.consider_patrol_requests(self.consider_patrol)
        name = names[0]
        if name not in c['robots'] or self.graph.find_waypoint(
                c['robots'][name]['charger']) is None:
            raise ValueError(f'Missing robot configuration or charger: {name}')
        self.commands[name] = HardwareCommand(self, name, self.adapter, c)
        self.lifecycle[name] = dict(
            client=self.create_client(GetState, f'/{name}/bt_navigator/get_state'),
            future=None, next_check=0.0)
        self.create_timer(1.0 / c['update_frequency'], self.tick)


def main(args=None):
    rclpy.init(args=args)
    rmf.init_rclcpp()
    node = HardwareFleetNode()
    try:
        node.start()
        rclpy.spin(node)
    finally:
        for command in node.commands.values():
            command.shutdown()
        deadline = time.monotonic() + 2.0
        while (rclpy.ok() and time.monotonic() < deadline
               and any(c.goal or c.backup_goal for c in node.commands.values())):
            rclpy.spin_once(node, timeout_sec=0.1)
        if node.adapter:
            node.adapter.stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
