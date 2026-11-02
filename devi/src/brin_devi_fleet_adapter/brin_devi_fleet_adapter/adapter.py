"""Onboard Devi adapter: native RMF domain 0, existing Nav2 domain 73."""
import os
import time

import rclpy
import rmf_adapter as rmf
from geometry_msgs.msg import Twist
from nav2_msgs.action import NavigateToPose

from .common import FleetNode
from .command import Nav2Command
from .gateway import Nav2Gateway, ActionProxy, LifecycleProxy, StopProxy
from .geometry import MapAlignment, require_commissioning
from .profiles import load_settings


class DeviCommand(Nav2Command):
    def __init__(self, *args):
        super().__init__(*args)
        self.behavior_tree = ''  # Existing installed Devi Nav2 default.

    def follow_new_path(self, waypoints, estimator, finished):
        if self.task_id is None:
            self.node.get_logger().warning('Devi: ignoring path without an active RMF task')
            return
        super().follow_new_path(waypoints, estimator, finished)

    def observe_task(self, task_id):
        previous = self.task_id
        super().observe_task(task_id)
        if self.task_id != previous:
            self.stop()
            if self.task_id is not None and self.update is not None:
                self.update.replan()

    def _start_escape(self):
        self._recovery_failed('Devi: operator intervention required; automatic reverse disabled')


class DeviFleetNode(FleetNode):
    command_type = DeviCommand

    def __init__(self):
        super().__init__()
        self.declare_parameter('integration_config', '')
        self.settings = load_settings(self.get_parameter('integration_config').value)
        require_commissioning(self.settings)
        self.alignment = MapAlignment(self.settings['map_alignment'])
        if self.get_parameter('use_sim_time').value:
            raise ValueError('Physical Devi requires real time')
        if list(self.get_parameter('robots').value) != ['devi']:
            raise ValueError('Only physical devi is supported')
        self.gateway = Nav2Gateway(self.settings, allow_commands=True)

    def nav2_action_client(self, action, _topic):
        return ActionProxy(self.gateway, supported=action is NavigateToPose)

    def create_publisher(self, message_type, topic, *args, **kwargs):
        if message_type is Twist and topic == '/devi/cmd_vel_nav':
            return StopProxy(self.gateway)
        return super().create_publisher(message_type, topic, *args, **kwargs)

    def start(self):
        super().start()
        self.lifecycle['devi']['client'] = LifecycleProxy(self.gateway)

    def pose_in_frame(self, name, frame):
        if (frame != 'map' or not self.gateway.fresh
                or not self.gateway.state.get('nav2_ready', False)):
            raise RuntimeError('Devi Nav2 gateway or localization is stale')
        return self.alignment.to_rmf(self.gateway.state['nav2_pose'])

    def to_nav2_pose(self, pose):
        return self.alignment.to_nav2(pose)

    def registered(self, name, update):
        update.enable_responsive_wait(False)
        super().registered(name, update)

    def tick(self):
        self.gateway.poll()
        super().tick()


def main(args=None):
    if os.environ.get('ROS_DOMAIN_ID') != '0':
        raise ValueError('Native RMF must use ROS_DOMAIN_ID=0; use tools/devi.bash')
    if os.environ.get('BRIN_ENABLE_DISPATCH') != '1':
        raise ValueError('Dispatch requires explicit BRIN_ENABLE_DISPATCH=1')
    # Check commissioning before starting any ROS process or publishers.
    from rclpy.utilities import remove_ros_args
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--integration-config', required=True)
    parsed = parser.parse_args(remove_ros_args(args=args)[1:])
    require_commissioning(load_settings(parsed.integration_config))
    rclpy.init(args=args, domain_id=0)
    rmf.init_rclcpp()
    node = None
    try:
        node = DeviFleetNode()
        node.start()
        rclpy.spin(node)
    finally:
        if node is not None:
            for command in node.commands.values():
                command.shutdown()
            deadline = time.monotonic() + 2.0
            while (rclpy.ok() and time.monotonic() < deadline
                   and any(c.goal or c.backup_goal for c in node.commands.values())):
                rclpy.spin_once(node, timeout_sec=0.1)
            if node.adapter:
                node.adapter.stop()
            node.gateway.close()
            node.destroy_node()
        rclpy.try_shutdown()
