"""Serialize RMF commands and Nav2 actions; reject stale action callbacks."""
from datetime import timedelta
import math
from pathlib import Path
import queue
import time
import uuid
import numpy as np
from ament_index_python.packages import get_package_share_directory
import rmf_adapter as rmf
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import Twist
from nav2_msgs.action import BackUp, NavigateToPose
from nav2_msgs.msg import Costmap
from nav2_msgs.srv import ClearEntireCostmap
from rclpy.action import ActionClient
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from .escape_geometry import rear_sweep_clear, turn_space_clear


class Nav2Command(rmf.RobotCommandHandle):
    def __init__(self, node, name, adapter, config):
        super().__init__()
        self.node, self.name, self.adapter, self.config = node, name, adapter, config
        self.client = ActionClient(node, NavigateToPose, f'/{name}/navigate_to_pose')
        self.backup_client = ActionClient(node, BackUp, f'/{name}/backup')
        self.clear_client = node.create_client(
            ClearEntireCostmap,
            f'/{name}/local_costmap/clear_entirely_local_costmap')
        self.stop_publisher = node.create_publisher(Twist, f'/{name}/cmd_vel_nav', 10)
        self.costmap_subscription = node.create_subscription(
            Costmap, f'/{name}/local_costmap/costmap_raw',
            self._on_costmap, qos_profile_sensor_data)
        self.scan_subscription = node.create_subscription(
            LaserScan, f'/{name}/sensors/lidar3d_0/scan',
            self._on_scan, qos_profile_sensor_data)
        self.behavior_tree = str(Path(get_package_share_directory(
            'brin_husky_fleet_adapter'))/'config/rmf_bounded_navigation.xml')
        self.events = queue.SimpleQueue()
        self.epoch = 0
        self.path = []
        self.index = 0
        self.goal = None
        self.sending = False
        self.canceling = False
        self.arrived = False
        self.estimator = None
        self.finished = None
        self.update = None
        self.pose = None
        self.issue = None
        self.recovery_issue = None
        self.navigation_ready = False
        self.retry_after = 0.0
        self.task_id = None
        self.origin_waypoint = None
        self.last_graph_waypoint = None
        self.first_path_origin = None
        self.failure_count = 0
        self.recovery_state = None
        self.recovery_task_id = None
        self.pending_recovery_path = None
        self.kill_pending_since = None
        self.local_costmap = None
        self.costmap_at = 0.0
        self.scan_at = 0.0
        self.escape_first_scan_at = None
        self.escape_sensor_after = 0.0
        self.escape_settle_until = 0.0
        self.escape_deadline = 0.0
        self.escape_steps = 0
        self.escape_start_pose = None
        self.clear_future = None
        self.backup_send_future = None
        self.backup_goal = None
        self.shutdown_requested = False

    def _on_costmap(self, message):
        self.local_costmap = message
        self.costmap_at = time.monotonic()

    def _on_scan(self, _message):
        self.scan_at = time.monotonic()
        if (self.recovery_state == 'escape_settle'
                and self.escape_first_scan_at is None
                and self.scan_at > self.escape_sensor_after):
            self.escape_first_scan_at = self.scan_at

    def _halt(self):
        self.stop_publisher.publish(Twist())

    def shutdown(self):
        """Cancel every action on intentional adapter shutdown."""
        self.shutdown_requested = True
        self.path, self.finished = [], None
        self.epoch += 1
        self._cancel()
        if self.backup_goal is not None:
            self.backup_goal.cancel_goal_async()
        self._halt()

    # Invoked from RMF's C++ executor. ROS action work stays in the rclpy thread.
    def follow_new_path(self, waypoints, next_arrival_estimator, path_finished_callback):
        self.events.put(('path', list(waypoints), next_arrival_estimator, path_finished_callback))

    def stop(self):
        self.events.put(('stop',))

    def dock(self, dock_name, docking_finished_callback):
        # This milestone parks at charger vertices and does not emulate docking.
        self.events.put(('dock', dock_name))

    def next_graph_waypoint(self):
        """Return the next known graph target for off-grid position reports."""
        for waypoint in self.path[self.index:]:
            graph_index = getattr(waypoint, 'graph_index', None)
            if graph_index is not None:
                return int(graph_index)
        return None

    def observe_task(self, task_id):
        """Track the authoritative RMF task ID published in /fleet_states."""
        task_id = task_id or None
        if self.recovery_state is not None:
            if self.recovery_state == 'recovery_failed':
                return
            if self.recovery_state == 'kill_pending':
                if self.task_id is None and task_id is not None:
                    self.task_id = task_id
                if self.origin_waypoint is None:
                    self.origin_waypoint = (
                        self.first_path_origin if self.first_path_origin is not None
                        else self.last_graph_waypoint)
                self._start_kill()
                return
            if (self.recovery_state in ('return_requested', 'returning')
                    and task_id == self.recovery_task_id
                    and task_id is not None):
                self.recovery_state = 'returning'
            elif (self.recovery_state == 'returning'
                  and task_id != self.recovery_task_id):
                if (self.pose is not None
                        and self.origin_waypoint is not None
                        and self.node.distance_to_waypoint(
                            self.origin_waypoint, self.pose)
                        <= self.config.get('return_tolerance', 0.75)):
                    self.node.get_logger().info(
                        f'{self.name}: returned to original waypoint '
                        f'{self.origin_waypoint} after task failure')
                    if self.issue is not None:
                        self.issue.resolve({'detail': 'Returned to original waypoint'})
                        self.issue = None
                    self._reset_task(task_id)
                else:
                    self._recovery_failed('Recovery task ended before reaching origin')
            return
        if task_id != self.task_id:
            self._reset_task(task_id)

    def _reset_task(self, task_id):
        self.task_id = task_id
        self.origin_waypoint = (
            self.first_path_origin if task_id and self.first_path_origin is not None
            else self.last_graph_waypoint if task_id else None)
        self.first_path_origin = None
        self.failure_count = 0
        self.recovery_state = None
        self.recovery_task_id = None
        self.pending_recovery_path = None
        self.kill_pending_since = None

    def _start_kill(self):
        if self.recovery_state != 'kill_pending':
            return
        if self.task_id is None or self.origin_waypoint is None:
            return
        task_id = self.task_id
        self.recovery_state = 'kill_requested'
        labels = [f'Nav2 navigation failed {self.failure_count} times',
                  'Safe escape assessment required before return']
        self.update.kill_task(
            task_id, labels,
            lambda found: self.events.put(('kill_result', task_id, found)))
        self.node.get_logger().error(
            f'{self.name}: killing RMF task {task_id} after '
            f'{self.failure_count} Nav2 failures; return waypoint '
            f'{self.origin_waypoint}')

    def _start_escape(self):
        if self.pose is None:
            self._recovery_failed('No current TF pose available for escape')
            return
        self.recovery_state = 'escape_clear'
        self.escape_steps = 0
        self.clear_future = None
        self.escape_deadline = time.monotonic()+self.config.get('escape_service_timeout', 5.0)
        self._halt()
        try:
            footprint = self.config['profile']['footprint']
            vicinity = self.config['profile']['vicinity']
            bubble = self.config.get('escape_step_distance', 0.20)+0.05
            self.update.unstable_change_participant_profile(
                footprint+bubble, vicinity+bubble)
            self.update.unstable_declare_holding(
                self.config['map_name'], np.asarray(self.pose, dtype=float),
                self.config.get('escape_hold_duration', 20.0))
        except Exception as exc:
            self._recovery_failed(f'RMF could not hold escape area: {exc}')
            return
        self.node.get_logger().warning(
            f'{self.name}: failed task killed; clearing local costmap before '
            'collision-checked escape')

    def _wait_for_fresh_costmap(self, now, settle):
        self.recovery_state = 'escape_settle'
        self.escape_sensor_after = now
        self.escape_first_scan_at = None
        self.escape_settle_until = now+settle
        self.escape_deadline = now+settle+self.config.get('escape_sensor_timeout', 5.0)

    def _escape_tick(self):
        now = time.monotonic()
        state = self.recovery_state
        if state == 'escape_clear':
            if now > self.escape_deadline:
                self._recovery_failed('Local costmap clear service timed out')
            elif self.clear_future is None:
                if self.clear_client.service_is_ready():
                    try:
                        self.clear_future = self.clear_client.call_async(
                            ClearEntireCostmap.Request())
                    except Exception as exc:
                        self._recovery_failed(f'Local costmap clear request failed: {exc}')
            elif self.clear_future.done():
                try:
                    self.clear_future.result()
                except Exception as exc:
                    self._recovery_failed(f'Local costmap clear failed: {exc}')
                    return
                self._wait_for_fresh_costmap(
                    now, self.config.get('escape_sensor_settle', 1.5))
            return
        if state == 'escape_settle':
            if now > self.escape_deadline:
                self._recovery_failed('No fresh lidar and local costmap after clear/backup')
            elif (now >= self.escape_settle_until
                  and self.escape_first_scan_at is not None
                  and self.costmap_at > self.escape_first_scan_at
                  and now-self.costmap_at <= self.config.get('escape_costmap_max_age', 2.0)):
                self.recovery_state = 'escape_check'
                self.escape_deadline = now+2.0
            return
        if state == 'escape_check':
            if self.pose is None or self.local_costmap is None:
                if now > self.escape_deadline:
                    self._recovery_failed('TF pose or local costmap unavailable for escape')
                return
            if now-self.costmap_at > self.config.get('escape_costmap_max_age', 2.0):
                self._recovery_failed('Local costmap stale before BackUp')
                return
            try:
                pose = self.node.pose_in_frame(
                    self.name, self.local_costmap.header.frame_id)
            except Exception as exc:
                if now > self.escape_deadline:
                    self._recovery_failed(f'Cannot locate robot in local costmap: {exc}')
                return
            if self.escape_steps and turn_space_clear(
                    self.local_costmap, pose,
                    self.config.get('escape_turn_radius', 0.70)):
                self.node.get_logger().info(
                    f'{self.name}: escape verified after {self.escape_steps} '
                    'BackUp steps; requesting scheduled RMF return')
                self._request_return()
                return
            limit = self.config.get('escape_max_steps', 3)
            if self.escape_steps >= limit:
                self._recovery_failed(
                    f'No safe turning space after {limit} BackUp steps')
                return
            distance = self.config.get('escape_step_distance', 0.20)
            speed = self.config.get('escape_backup_speed', 0.05)
            if not (0.15 <= distance <= 0.25 and 0 < speed <= 0.10):
                self._recovery_failed('Unsafe BackUp distance or speed configuration')
                return
            if not rear_sweep_clear(self.local_costmap, pose, distance):
                self._recovery_failed('Rear path blocked in fresh local costmap')
                return
            if not self.backup_client.server_is_ready():
                if now > self.escape_deadline:
                    self._recovery_failed('Nav2 BackUp action unavailable')
                return
            try:
                # Keep RMF aware of the actual pose while the failed task has
                # no itinerary; each short escape step remains within this hold.
                self.update.unstable_declare_holding(
                    self.config['map_name'], np.asarray(self.pose, dtype=float),
                    self.config.get('escape_hold_duration', 20.0))
            except Exception as exc:
                self._recovery_failed(f'RMF could not declare escape hold: {exc}')
                return
            goal = BackUp.Goal()
            goal.target.x = -distance
            goal.speed = speed
            goal.time_allowance.sec = int(math.ceil(distance/goal.speed)+5)
            self.escape_start_pose = tuple(self.pose)
            try:
                self.backup_send_future = self.backup_client.send_goal_async(goal)
            except Exception as exc:
                self._recovery_failed(f'Nav2 BackUp request failed: {exc}')
                return
            self.backup_send_future.add_done_callback(
                lambda future: self.events.put(('escape_accepted', future)))
            self.recovery_state = 'escape_sending'
            self.escape_deadline = now+self.config.get('escape_service_timeout', 5.0)
            self.node.get_logger().info(
                f'{self.name}: collision-checked BackUp step '
                f'{self.escape_steps+1}/{limit}, {distance:.2f} m')
            return
        if state in ('escape_sending', 'escape_moving', 'escape_verify'):
            if now > self.escape_deadline:
                self._recovery_failed(f'Nav2 BackUp {state} timed out')
                return
            if state == 'escape_verify' and self.pose is not None:
                start = self.escape_start_pose
                traveled = -((self.pose[0]-start[0])*math.cos(start[2])
                             +(self.pose[1]-start[1])*math.sin(start[2]))
                distance = self.config.get('escape_step_distance', 0.20)
                if traveled >= 0.7*distance:
                    self.escape_steps += 1
                    self._wait_for_fresh_costmap(
                        now, self.config.get('escape_after_step_settle', 0.5))

    def _escape_accepted(self, future):
        try:
            handle = future.result()
        except Exception as exc:
            if self.recovery_state == 'escape_sending':
                self._recovery_failed(f'Nav2 BackUp submission failed: {exc}')
            return
        if self.recovery_state != 'escape_sending' or self.shutdown_requested:
            if handle.accepted:
                handle.cancel_goal_async()
            return
        if not handle.accepted:
            self._recovery_failed('Nav2 rejected BackUp goal')
            return
        self.backup_goal = handle
        handle.get_result_async().add_done_callback(
            lambda result: self.events.put(('escape_result', result)))
        self.recovery_state = 'escape_moving'
        distance = self.config.get('escape_step_distance', 0.20)
        speed = self.config.get('escape_backup_speed', 0.05)
        self.escape_deadline = time.monotonic()+distance/speed+8.0

    def _escape_result(self, future):
        self.backup_goal = None
        if self.recovery_state != 'escape_moving':
            return
        try:
            status = future.result().status
        except Exception as exc:
            self._recovery_failed(f'Nav2 BackUp result error: {exc}')
            return
        if status != GoalStatus.STATUS_SUCCEEDED:
            self._recovery_failed(f'Nav2 BackUp failed with status {status}')
            return
        self.recovery_state = 'escape_verify'
        self.escape_deadline = time.monotonic()+2.0

    def _request_return(self):
        try:
            self.update.unstable_change_participant_profile(
                self.config['profile']['footprint'],
                self.config['profile']['vicinity'])
        except Exception as exc:
            self._recovery_failed(f'RMF could not restore robot profile: {exc}')
            return
        request_id = f'brin_recovery_{self.name}_{uuid.uuid4()}'
        self.recovery_state = 'return_requested'
        request = {
            'category': 'patrol',
            'description': {'places': [self.origin_waypoint], 'rounds': 1},
            'labels': [f'Return after failed task {self.task_id}'],
            'requester': 'brin_husky_fleet_adapter',
        }
        self.update.submit_direct_request(
            request, request_id,
            lambda response: self.events.put(
                ('return_response', request_id, response)))

    def _recovery_failed(self, reason):
        if self.recovery_state == 'recovery_failed':
            return
        self.recovery_state = 'recovery_failed'
        self.path, self.finished, self.pending_recovery_path = [], None, None
        self.epoch += 1
        self._cancel()
        if self.backup_goal is not None:
            self.backup_goal.cancel_goal_async()
        self._halt()
        self.node.get_logger().error(f'{self.name}: {reason}; operator intervention required')
        if self.recovery_issue is None:
            self.recovery_issue = self.update.create_issue(
                rmf.robot_update_handle.Tier.Error, 'recovery',
                {'detail': f'{reason}; operator intervention required',
                 'original_task': self.task_id,
                 'origin_waypoint': self.origin_waypoint})
        if self.recovery_task_id is not None:
            self.update.kill_task(
                self.recovery_task_id, [reason],
                lambda found: self.node.get_logger().warning(
                    f'{self.name}: recovery task kill acknowledged: {found}'))
        self.update.unstable_decommission()

    def _cancel(self):
        if self.goal is not None and not self.canceling:
            self.canceling = True
            future = self.goal.cancel_goal_async()
            future.add_done_callback(self._canceled)

    def _canceled(self, future):
        try:
            if not future.result().goals_canceling:
                self.node.get_logger().warning(f'{self.name}: goal was already terminal or cancellation rejected')
        except Exception as exc:
            self.node.get_logger().error(f'{self.name}: cancellation error: {exc}')
        # Wait for the action result, not just the cancel acknowledgement,
        # before issuing the next path. The controller must actually stop.

    def fail(self, reason, *, count_goal_failure=False):
        self.epoch += 1
        self.path = []
        self.finished = None
        self.retry_after = time.monotonic()+self.config.get('retry_delay', 5.0)
        self.node.get_logger().error(f'{self.name}: {reason}')
        self._cancel()
        if self.update is not None:
            if self.issue is None:
                self.issue = self.update.create_issue(rmf.robot_update_handle.Tier.Error,
                                                     'nav2', {'detail': reason})
            if not count_goal_failure:
                if self.recovery_state in (None, 'returning'):
                    self.update.replan()
                return
            self.failure_count += 1
            limit = self.config.get('max_goal_failures', 5)
            if self.failure_count >= limit:
                if self.recovery_state == 'returning':
                    self._recovery_failed(
                        f'Return navigation failed {self.failure_count} times')
                elif self.recovery_state is None:
                    self._halt()
                    self.recovery_state = 'kill_pending'
                    self.kill_pending_since = time.monotonic()
                    self._start_kill()
            elif self.recovery_state in (None, 'returning'):
                self.update.replan()

    def tick(self):
        while not self.events.empty():
            event = self.events.get_nowait()
            if event[0] == 'escape_accepted':
                self._escape_accepted(event[1])
                continue
            if event[0] == 'escape_result':
                self._escape_result(event[1])
                continue
            if event[0] == 'kill_result':
                if self.recovery_state == 'kill_requested' and event[1] == self.task_id:
                    if event[2]:
                        self._start_escape()
                    else:
                        self._recovery_failed('RMF did not find the failed task to kill')
                continue
            if event[0] == 'return_response':
                if self.recovery_state == 'return_requested':
                    response = event[2]
                    booking = response.get('state', {}).get('booking', {})
                    if response.get('success') and booking.get('id'):
                        self.recovery_task_id = booking['id']
                        self.failure_count = 0
                        self.node.get_logger().info(
                            f'{self.name}: RMF return task {self.recovery_task_id} '
                            f'queued for waypoint {self.origin_waypoint}')
                    else:
                        self._recovery_failed(f'RMF rejected return task: {response}')
                continue
            if self.shutdown_requested:
                continue
            self.epoch += 1
            self._cancel()
            self.path, self.finished, self.estimator = [], None, None
            self.index, self.arrived = 0, False
            if event[0] == 'path':
                if self.recovery_state == 'return_requested':
                    self.pending_recovery_path = event
                elif self.recovery_state in ('kill_pending', 'kill_requested',
                                             'recovery_failed'):
                    continue
                elif (self.recovery_state is not None
                      and self.recovery_state.startswith('escape_')):
                    continue
                else:
                    if self.task_id is None and self.first_path_origin is None:
                        self.first_path_origin = self.last_graph_waypoint
                    self.path, self.estimator, self.finished = event[1:]
            elif event[0] == 'stop':
                self.pending_recovery_path = None
                if self.task_id is None:
                    self.first_path_origin = None
            elif event[0] == 'dock':
                self.fail(f'Docking {event[1]} is unsupported; use park finishing behavior')
        self._start_kill()
        if self.shutdown_requested:
            return
        if (self.recovery_state == 'kill_pending'
                and time.monotonic()-self.kill_pending_since > 10.0):
            self._recovery_failed('No RMF task ID or origin waypoint available')
        if self.recovery_state and self.recovery_state.startswith('escape_'):
            if not self.shutdown_requested:
                self._escape_tick()
            return
        if self.recovery_state == 'returning' and self.pending_recovery_path:
            event, self.pending_recovery_path = self.pending_recovery_path, None
            self.path, self.estimator, self.finished = event[1:]
            self.index, self.arrived = 0, False
        if self.sending or self.goal is not None or self.canceling:
            return
        if not self.path:
            if self.finished is not None:
                done, self.finished = self.finished, None
                done()
            return
        if self.pose is None or not self.navigation_ready or time.monotonic() < self.retry_after:
            return
        if self.arrived:
            # Preserve RMF's planned holds. Early arrival must not cause an
            # early departure into a lane reserved for another participant.
            if self.adapter.now() < self.path[self.index].time:
                if self.estimator:
                    self.estimator(self.index, timedelta(seconds=0))
                return
            self.index += 1
            self.arrived = False
        if self.index >= len(self.path):
            done = self.finished
            self.path, self.finished = [], None
            if self.issue is not None and self.recovery_state is None:
                self.issue.resolve({'detail': 'navigation recovered'})
                self.issue = None
            if done:
                done()
            return
        target = self.path[self.index]
        if not self.client.server_is_ready():
            return
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = self.node.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(target.position[0])
        goal.pose.pose.position.y = float(target.position[1])
        goal.pose.pose.orientation.z = math.sin(float(target.position[2])/2)
        goal.pose.pose.orientation.w = math.cos(float(target.position[2])/2)
        goal.behavior_tree = self.behavior_tree
        self.sending = True
        epoch = self.epoch
        future = self.client.send_goal_async(goal, feedback_callback=lambda msg: self.feedback(epoch, msg))
        future.add_done_callback(lambda f: self.accepted(epoch, f))
        self.node.get_logger().info(f'{self.name}: Nav2 waypoint {self.index+1}/{len(self.path)}')

    def accepted(self, epoch, future):
        self.sending = False
        try:
            handle = future.result()
        except Exception as exc:
            if epoch == self.epoch:
                self.fail(f'Goal submission failed: {exc}', count_goal_failure=True)
            return
        if not handle.accepted:
            if epoch == self.epoch:
                self.fail('Nav2 rejected goal', count_goal_failure=True)
            return
        self.goal = handle
        handle.get_result_async().add_done_callback(lambda f: self.result(epoch, f))
        # stop() can arrive before Nav2 acknowledges send_goal_async().
        if epoch != self.epoch:
            self._cancel()

    def result(self, epoch, future):
        self.goal, self.canceling = None, False
        if epoch != self.epoch:
            return
        try:
            status = future.result().status
        except Exception as exc:
            self.fail(f'Nav2 result error: {exc}', count_goal_failure=True)
            return
        if status == GoalStatus.STATUS_SUCCEEDED:
            self.arrived = True
        else:
            self.fail(f'Nav2 terminated with status {status}; RMF path remains incomplete',
                      count_goal_failure=True)

    def feedback(self, epoch, message):
        if epoch != self.epoch or self.estimator is None or not self.path:
            return
        feedback = message.feedback
        seconds = feedback.estimated_time_remaining.sec + feedback.estimated_time_remaining.nanosec/1e9
        if seconds <= 0:
            seconds = feedback.distance_remaining / self.config['limits']['linear'][0]
        self.estimator(self.index, timedelta(seconds=max(0.0, seconds)))
