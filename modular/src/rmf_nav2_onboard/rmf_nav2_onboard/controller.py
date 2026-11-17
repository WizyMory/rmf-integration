"""ROS-independent RMF waypoint/action state machine. Call tick in one thread."""
from datetime import timedelta
import math
import queue
import time
import uuid


class Controller:
    def __init__(self, config, gateway, alignment, now, log, failed, replan, transit_tree='', completed=lambda: None):
        self.config, self.gateway, self.alignment = config, gateway, alignment
        self.now, self.log, self.failed, self.replan = now, log, failed, replan
        self.transit_tree = transit_tree
        self.completed = completed
        self.events = queue.SimpleQueue()
        self.path, self.index, self.finished, self.estimator = [], 0, None, None
        self.active, self.sent_at, self.cancel_requested = None, 0., False
        self.arrived, self.task_id = False, None
        self.failures, self.retry_at, self.retry_pending = 0, 0., False

    def follow(self, waypoints, estimator, finished):
        self.events.put(('path', list(waypoints), estimator, finished))

    def stop(self):
        self.events.put(('stop',))

    def task(self, task_id):
        self.events.put(('task', task_id or None))

    def dock(self, name):
        self.events.put(('dock', name))

    def cancel(self):
        if self.active is not None and not self.cancel_requested:
            self.gateway.send('cancel', id=self.active)
            self.cancel_requested = True

    def fault(self, reason):
        self.cancel()
        self.path, self.finished, self.estimator = [], None, None
        self.arrived = False
        self.failures += 1
        self.failed(reason)
        self.retry_at = time.monotonic()+3
        self.retry_pending = self.failures < 3

    def tick(self, state, incoming=(), ready=True):
        while not self.events.empty():
            event = self.events.get()
            if event[0] == 'task':
                if event[1] != self.task_id:
                    self.cancel()
                    self.path, self.finished = [], None
                    self.task_id = event[1]
                    self.failures, self.retry_pending = 0, bool(self.task_id)
                    self.retry_at = time.monotonic()
            elif event[0] == 'path' and self.task_id is not None:
                self.cancel()
                self.path, self.estimator, self.finished = event[1:]
                self.index, self.arrived, self.retry_pending = 0, False, False
            elif event[0] == 'stop':
                self.cancel()
                self.path, self.finished = [], None
                self.retry_pending = False
            elif event[0] == 'dock':
                self.fault('Docking is unsupported: '+event[1])
                self.retry_pending = False
        for event in incoming:
            if event.get('id') != self.active:
                continue
            kind = event['kind']
            if kind == 'feedback' and self.path and not self.cancel_requested:
                remaining = event['remaining']
                if math.isfinite(remaining) and remaining >= 0:
                    self.estimator(self.index, timedelta(seconds=remaining))
            elif kind == 'accepted' and not event['accepted']:
                self.active, self.cancel_requested = None, False
                self.fault('Nav2 rejected the goal')
            elif kind == 'error':
                # Submission uncertainty is not proof the robot has stopped.
                # Keep the action ID until result/cancel is confirmed.
                self.fault(event['error'])
            elif kind == 'result':
                cancelled = self.cancel_requested
                self.active, self.cancel_requested = None, False
                if not cancelled:
                    if event['status'] == 4:  # action_msgs/GoalStatus.STATUS_SUCCEEDED
                        self.arrived = True
                    else:
                        self.fault('Nav2 ended with status '+str(event['status']))
        if not ready:
            if (self.active is not None and not self.cancel_requested) or self.path:
                self.fault('Navigation/core readiness lost; RMF path remains incomplete')
            return
        if self.active is not None:
            if not self.cancel_requested and time.monotonic()-self.sent_at > self.config['nav2']['action_timeout']:
                # action_timeout bounds acknowledgement, not total travel time.
                # Accepted actions are tracked by result, without this timeout.
                self.fault('Nav2 acknowledgement timeout; awaiting owned action cancellation')
            return
        if self.retry_pending and self.task_id and time.monotonic() >= self.retry_at:
            self.retry_pending = False
            self.replan()
        if not self.path or state.get('pose') is None:
            return
        if self.arrived:
            if self.now() < self.path[self.index].time:
                self.estimator(self.index, timedelta(seconds=0))
                return
            self.index += 1
            self.arrived = False
        if self.index >= len(self.path):
            callback = self.finished
            self.path, self.finished = [], None
            self.failures = 0
            self.completed()
            if callback:
                callback()
            return
        target = self.path[self.index]
        transit = (self.config['nav2']['final_orientation_only']
                   and self.index < len(self.path)-1 and getattr(target, 'event', None) is None)
        self.active, self.cancel_requested = str(uuid.uuid4()), False
        self.sent_at = time.monotonic()
        self.gateway.send('goal', id=self.active,
            pose=self.alignment.to_nav2(target.position),
            behavior_tree=self.transit_tree if transit else '')
        rmf_pose = self.alignment.to_rmf(state['pose'])
        distance = math.hypot(target.position[0]-rmf_pose[0], target.position[1]-rmf_pose[1])
        self.estimator(self.index, timedelta(seconds=distance/self.config['motion']['linear_speed']))
        self.log(f'Nav2 waypoint {self.index+1}/{len(self.path)} '
                 f'({"position only" if transit else "position and yaw"})')

    def acknowledge(self, events):
        # Only the submission phase has a timeout. A journey can last minutes.
        for event in events:
            if event.get('id') == self.active and event['kind'] == 'accepted' and event['accepted']:
                self.sent_at = float('inf')

    def next_graph_waypoint(self):
        for target in self.path[self.index:]:
            if getattr(target, 'graph_index', None) is not None:
                return target.graph_index
        return None
