from concurrent.futures import Future
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import pytest
from action_msgs.msg import GoalStatus
from nav2_msgs.msg import Costmap
from brin_husky_fleet_adapter import command as module
from brin_husky_fleet_adapter.adapter import FleetNode


def completed(value):
    future = Future(); future.set_result(value)
    return future


class Goal:
    accepted = True
    def __init__(self):
        self.result = Future()
        self.cancellations = 0
    def cancel_goal_async(self):
        self.cancellations += 1
        return completed(SimpleNamespace(goals_canceling=[True]))
    def get_result_async(self):
        return self.result


class Client:
    def __init__(self, node, action, topic):
        self.topic = topic
        self.requests = []
    def server_is_ready(self):
        return True
    def send_goal_async(self, goal, feedback_callback=None):
        future = Future()
        self.requests.append((goal, future))
        return future


class Service:
    def __init__(self):
        self.calls = []
    def service_is_ready(self):
        return True
    def call_async(self, request):
        self.calls.append(request)
        return completed(SimpleNamespace())


class Publisher:
    def __init__(self):
        self.messages = []
    def publish(self, message):
        self.messages.append(message)


class Issue:
    def __init__(self):
        self.resolutions = []
    def resolve(self, detail):
        self.resolutions.append(detail)


class Update:
    def __init__(self):
        self.replans = 0
        self.kills = []
        self.requests = []
        self.issues = []
        self.decommissions = 0
        self.holds = []
        self.profiles = []
    def replan(self):
        self.replans += 1
    def create_issue(self, tier, category, detail):
        issue = Issue()
        self.issues.append((category, detail, issue))
        return issue
    def kill_task(self, task_id, labels, callback):
        self.kills.append((task_id, labels, callback))
    def submit_direct_request(self, request, request_id, callback):
        self.requests.append((request, request_id, callback))
    def unstable_decommission(self):
        self.decommissions += 1
    def unstable_declare_holding(self, map_name, pose, duration):
        self.holds.append((map_name, tuple(pose), duration))
    def unstable_change_participant_profile(self, footprint, vicinity):
        self.profiles.append((footprint, vicinity))


def clear_costmap():
    costmap = Costmap()
    costmap.header.frame_id = 'husky_0/odom'
    costmap.metadata.resolution = 0.05
    costmap.metadata.size_x = costmap.metadata.size_y = 120
    costmap.metadata.origin.position.x = -3.0
    costmap.metadata.origin.position.y = -3.0
    costmap.data = [0]*14400
    return costmap


@pytest.fixture
def robot(monkeypatch):
    monkeypatch.setattr(module, 'ActionClient', Client)
    logger = SimpleNamespace(info=lambda *a: None, error=lambda *a: None, warning=lambda *a: None)
    from builtin_interfaces.msg import Time
    service, publisher = Service(), Publisher()
    node = SimpleNamespace(get_logger=lambda: logger,
        get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(to_msg=lambda: Time())),
        distance_to_waypoint=lambda index, pose: 0.0,
        pose_in_frame=lambda name, frame: command.pose,
        create_client=lambda *args: service,
        create_publisher=lambda *args: publisher,
        create_subscription=lambda *args: object())
    adapter = SimpleNamespace(now=lambda: datetime(2026, 1, 1))
    command = module.Nav2Command(node, 'husky_0', adapter, {
        'limits': {'linear': [0.4, 0.3]}, 'retry_delay': 0,
        'max_goal_failures': 5, 'map_name': 'L1',
        'profile': {'footprint': 0.70, 'vicinity': 0.80},
        'escape_sensor_settle': 0, 'escape_after_step_settle': 0})
    command.pose = [0, 0, 0]
    command._on_costmap(clear_costmap())
    command.navigation_ready = True
    command.update = Update()
    return command


def waypoint(seconds=0, graph_index=1):
    return SimpleNamespace(position=[1.0, 2.0, 0.0],
        time=datetime(2026, 1, 1)+timedelta(seconds=seconds),
        graph_index=graph_index)


def test_next_graph_waypoint_skips_interpolated_points(robot):
    robot.path = [waypoint(graph_index=None), waypoint(graph_index=218)]
    assert robot.next_graph_waypoint() == 218
    robot.index = 1
    assert robot.next_graph_waypoint() == 218
    robot.path = [waypoint(graph_index=None)]
    assert robot.next_graph_waypoint() is None


def test_stop_during_pending_acceptance_cancels_late_goal(robot):
    finished = []
    robot.follow_new_path([waypoint()], lambda *args: None, lambda: finished.append(True))
    robot.tick()
    assert robot.client.topic == '/husky_0/navigate_to_pose'
    robot.stop(); robot.tick()
    goal = Goal(); robot.client.requests[0][1].set_result(goal)
    assert goal.cancellations == 1
    goal.result.set_result(SimpleNamespace(status=GoalStatus.STATUS_CANCELED))
    robot.tick()
    assert not finished and not robot.path and robot.goal is None


def test_rmf_goal_uses_bounded_nav2_tree(robot):
    tree_path = Path(robot.behavior_tree)
    assert tree_path.name == 'rmf_bounded_navigation.xml'
    source_tree = Path(__file__).resolve().parents[1]/'config'/tree_path.name
    root = ET.parse(source_tree).getroot()
    assert root.find('.//RateController/ComputePathToPose') is not None
    assert root.find('.//FollowPath') is not None
    assert root.find('.//RecoveryNode') is None

    robot.follow_new_path([waypoint()], lambda *args: None, lambda: None)
    robot.tick()
    assert robot.client.requests[0][0].behavior_tree == robot.behavior_tree


def test_replacement_waits_for_cancel_result(robot):
    robot.follow_new_path([waypoint()], lambda *args: None, lambda: None)
    robot.tick()
    old = Goal(); robot.client.requests[0][1].set_result(old)
    robot.follow_new_path([waypoint()], lambda *args: None, lambda: None)
    robot.tick()
    assert old.cancellations == 1 and len(robot.client.requests) == 1
    old.result.set_result(SimpleNamespace(status=GoalStatus.STATUS_CANCELED))
    robot.tick()
    assert len(robot.client.requests) == 2


def test_failure_never_reports_path_complete(robot):
    finished = []
    robot.follow_new_path([waypoint()], lambda *args: None, lambda: finished.append(True))
    robot.tick()
    goal = Goal(); robot.client.requests[0][1].set_result(goal)
    goal.result.set_result(SimpleNamespace(status=GoalStatus.STATUS_ABORTED))
    robot.tick()
    assert not finished and not robot.path


def test_early_arrival_preserves_scheduled_hold(robot):
    finished = []
    robot.follow_new_path([waypoint(10)], lambda *args: None, lambda: finished.append(True))
    robot.tick()
    goal = Goal(); robot.client.requests[0][1].set_result(goal)
    goal.result.set_result(SimpleNamespace(status=GoalStatus.STATUS_SUCCEEDED))
    robot.tick()
    assert not finished
    robot.adapter.now = lambda: datetime(2026, 1, 1)+timedelta(seconds=10)
    robot.tick()
    assert finished == [True]


def test_rejected_goal_does_not_finish(robot):
    finished = []
    robot.follow_new_path([waypoint()], lambda *args: None, lambda: finished.append(True))
    robot.tick()
    robot.client.requests[0][1].set_result(SimpleNamespace(accepted=False))
    robot.tick()
    assert not finished and not robot.sending and not robot.path


def abort_path(robot):
    robot.follow_new_path([waypoint()], lambda *args: None, lambda: None)
    robot.tick()
    goal = Goal()
    robot.client.requests[-1][1].set_result(goal)
    goal.result.set_result(SimpleNamespace(status=GoalStatus.STATUS_ABORTED))
    robot.tick()


def start_return(robot):
    robot.last_graph_waypoint = 3
    robot.observe_task('patrol-1')
    for _ in range(5):
        abort_path(robot)
    assert robot.recovery_state == 'kill_requested'
    robot.update.kills[0][2](True)
    robot.tick()
    complete_escape(robot)
    request, request_id, respond = robot.update.requests[0]
    respond({'success': True, 'state': {'booking': {'id': request_id}}})
    robot.tick()
    return request_id


def complete_escape(robot):
    if robot.recovery_state == 'escape_clear':
        robot.tick()
    assert robot.recovery_state == 'escape_settle'
    robot._on_scan(None)
    robot._on_costmap(clear_costmap())
    robot.tick()
    robot.tick()
    assert robot.recovery_state == 'escape_sending'
    assert robot.update.holds
    assert robot.update.profiles[0] == pytest.approx((0.95, 1.05))
    backup = Goal()
    robot.backup_client.requests[-1][1].set_result(backup)
    robot.tick()
    assert robot.recovery_state == 'escape_moving'
    backup.result.set_result(SimpleNamespace(status=GoalStatus.STATUS_SUCCEEDED))
    robot.pose = [-0.2, 0, 0]
    robot.tick()
    assert robot.recovery_state == 'escape_settle'
    robot._on_scan(None)
    robot._on_costmap(clear_costmap())
    robot.tick()
    robot.tick()
    assert robot.recovery_state == 'return_requested'
    assert robot.update.profiles[-1] == pytest.approx((0.70, 0.80))


def begin_escape_check(robot):
    robot.last_graph_waypoint = 3
    robot.observe_task('patrol-1')
    for _ in range(5):
        abort_path(robot)
    robot.update.kills[0][2](True)
    robot.tick()
    robot.tick()
    assert robot.recovery_state == 'escape_settle'
    robot._on_scan(None)
    robot._on_costmap(robot.local_costmap)
    robot.tick()
    assert robot.recovery_state == 'escape_check'


def test_escape_waits_for_sensor_repopulation_and_fails_closed(robot):
    robot.last_graph_waypoint = 3
    robot.observe_task('patrol-1')
    for _ in range(5):
        abort_path(robot)
    robot.update.kills[0][2](True)
    robot.tick()
    robot.tick()
    assert robot.recovery_state == 'escape_settle'
    assert not robot.backup_client.requests and not robot.update.requests
    robot.escape_deadline = module.time.monotonic()-1
    robot.tick()
    assert robot.recovery_state == 'recovery_failed'
    assert robot.update.decommissions == 1
    assert not robot.backup_client.requests
    assert 'operator intervention required' in robot.update.issues[-1][1]['detail']


def test_blocked_rear_path_never_sends_backup_or_return(robot):
    begin_escape_check(robot)
    blocked = clear_costmap()
    blocked.data[60*120+46] = 254  # 0.7 m behind the base frame
    robot._on_costmap(blocked)
    robot.tick()
    assert robot.recovery_state == 'recovery_failed'
    assert robot.update.decommissions == 1
    assert not robot.backup_client.requests
    assert not robot.update.requests


def test_aborted_backup_requires_operator_without_return_task(robot):
    begin_escape_check(robot)
    robot.tick()
    backup = Goal()
    robot.backup_client.requests[-1][1].set_result(backup)
    robot.tick()
    backup.result.set_result(SimpleNamespace(status=GoalStatus.STATUS_ABORTED))
    robot.tick()
    assert robot.recovery_state == 'recovery_failed'
    assert robot.update.decommissions == 1
    assert not robot.update.requests


def test_backup_success_without_tf_motion_does_not_authorize_return(robot):
    begin_escape_check(robot)
    robot.tick()
    backup = Goal()
    robot.backup_client.requests[-1][1].set_result(backup)
    robot.tick()
    backup.result.set_result(SimpleNamespace(status=GoalStatus.STATUS_SUCCEEDED))
    robot.tick()
    assert robot.recovery_state == 'escape_verify'
    assert not robot.update.requests
    robot.escape_deadline = module.time.monotonic()-1
    robot.tick()
    assert robot.recovery_state == 'recovery_failed'
    assert robot.update.decommissions == 1


def test_shutdown_cancels_active_backup_and_sends_zero_velocity(robot):
    begin_escape_check(robot)
    robot.tick()
    backup = Goal()
    robot.backup_client.requests[-1][1].set_result(backup)
    robot.tick()
    robot.shutdown()
    assert backup.cancellations == 1
    assert robot.shutdown_requested
    assert robot.stop_publisher.messages[-1].linear.x == 0.0
    assert not robot.update.requests


def test_three_safe_reverse_steps_without_turning_room_stop_for_operator(robot):
    begin_escape_check(robot)
    blocked_turn = clear_costmap()
    blocked_turn.data[70*120+50] = 254  # (-0.5, 0.5), outside rear rectangle
    for step in range(3):
        robot._on_costmap(blocked_turn)
        robot.tick()
        backup = Goal()
        robot.backup_client.requests[-1][1].set_result(backup)
        robot.tick()
        backup.result.set_result(SimpleNamespace(status=GoalStatus.STATUS_SUCCEEDED))
        robot.pose = [-0.2*(step+1), 0, 0]
        robot.tick()
        assert robot.recovery_state == 'escape_settle'
        robot._on_scan(None)
        robot._on_costmap(blocked_turn)
        robot.tick()
        robot.tick()
    assert robot.recovery_state == 'recovery_failed'
    assert robot.escape_steps == 3
    assert robot.update.decommissions == 1
    assert not robot.update.requests


def test_late_backup_acceptance_after_failure_is_canceled(robot):
    begin_escape_check(robot)
    robot.tick()
    robot.escape_deadline = module.time.monotonic()-1
    robot.tick()
    assert robot.recovery_state == 'recovery_failed'
    late = Goal()
    robot.backup_client.requests[-1][1].set_result(late)
    robot.tick()
    assert late.cancellations == 1
    assert not robot.update.requests


def test_five_final_nav2_aborts_kill_rmf_task_and_request_scheduled_return(robot):
    robot.last_graph_waypoint = 3
    robot.observe_task('patrol-1')
    finished = []
    for count in range(1, 5):
        robot.follow_new_path([waypoint()], lambda *args: None,
                              lambda: finished.append(True))
        robot.tick()
        goal = Goal()
        robot.client.requests[-1][1].set_result(goal)
        goal.result.set_result(SimpleNamespace(status=GoalStatus.STATUS_ABORTED))
        robot.tick()
        assert robot.failure_count == count
        assert robot.update.replans == count
        assert not robot.update.kills
    abort_path(robot)
    assert not finished
    assert robot.failure_count == 5
    assert robot.update.replans == 4
    assert robot.update.kills[0][0] == 'patrol-1'
    assert robot.origin_waypoint == 3
    assert robot.update.issues[0][0] == 'nav2'
    robot.update.kills[0][2](True)
    robot.tick()
    assert not robot.update.requests
    assert robot.recovery_state == 'escape_clear'
    complete_escape(robot)
    request, _, _ = robot.update.requests[0]
    assert request['category'] == 'patrol'
    assert request['description'] == {'places': [3], 'rounds': 1}


def test_return_waits_for_rmf_task_identity_and_resolves_only_after_arrival(robot):
    return_id = start_return(robot)
    finished = []
    robot.follow_new_path([waypoint()], lambda *args: None,
                          lambda: finished.append(True))
    count_before_return = len(robot.client.requests)
    robot.tick()
    assert len(robot.client.requests) == count_before_return
    assert robot.pending_recovery_path is not None
    robot.observe_task(return_id)
    robot.tick()
    goal = Goal()
    robot.client.requests[-1][1].set_result(goal)
    goal.result.set_result(SimpleNamespace(status=GoalStatus.STATUS_SUCCEEDED))
    robot.tick()
    assert finished == [True]
    assert robot.issue is not None
    robot.observe_task('ParkRobot-next')
    assert robot.issue is None
    assert robot.failure_count == 0
    assert robot.recovery_state is None
    assert robot.update.issues[0][2].resolutions


def test_return_rejection_decommissions_and_keeps_failure_issue(robot):
    robot.last_graph_waypoint = 3
    robot.observe_task('patrol-1')
    for _ in range(5):
        abort_path(robot)
    robot.update.kills[0][2](True)
    robot.tick()
    complete_escape(robot)
    robot.update.requests[0][2]({'success': False, 'errors': ['blocked']})
    robot.tick()
    assert robot.recovery_state == 'recovery_failed'
    assert robot.update.decommissions == 1
    assert robot.issue is not None
    assert robot.update.replans == 4


def test_return_ending_away_from_origin_requires_operator(robot):
    return_id = start_return(robot)
    robot.observe_task(return_id)
    robot.node.distance_to_waypoint = lambda index, pose: 2.0
    robot.observe_task(None)
    assert robot.recovery_state == 'recovery_failed'
    assert robot.update.decommissions == 1
    assert [issue[0] for issue in robot.update.issues] == ['nav2', 'recovery']


def test_missing_task_identity_times_out_without_killing_an_unknown_task(robot):
    for _ in range(5):
        abort_path(robot)
    robot.kill_pending_since -= 11.0
    robot.tick()
    assert robot.recovery_state == 'recovery_failed'
    assert robot.update.decommissions == 1
    assert robot.update.kills == []


def test_delayed_task_identity_still_kills_the_fifth_failed_goal(robot):
    robot.last_graph_waypoint = 3
    for _ in range(5):
        abort_path(robot)
    assert robot.recovery_state == 'kill_pending'
    assert not robot.update.kills
    robot.observe_task('late-patrol')
    assert robot.task_id == 'late-patrol'
    assert robot.origin_waypoint == 3
    assert len(robot.update.kills) == 1
    robot.observe_task('late-patrol')
    assert len(robot.update.kills) == 1


def test_five_aborts_during_return_stop_retries_and_decommission(robot):
    return_id = start_return(robot)
    robot.observe_task(return_id)
    for count in range(1, 6):
        abort_path(robot)
        assert robot.failure_count == count
    assert robot.recovery_state == 'recovery_failed'
    assert robot.update.decommissions == 1
    assert [task for task, _, _ in robot.update.kills] == ['patrol-1', return_id]
    assert robot.issue is not None


def test_recovery_task_accepts_an_installed_graph_index():
    graph = SimpleNamespace(num_waypoints=215,
                            find_waypoint=lambda place: object() if place == 'pantry' else None)
    fleet = SimpleNamespace(graph=graph)
    assert FleetNode.consider_patrol(fleet, {'places': [3]}).is_accepted()
    assert FleetNode.consider_patrol(fleet, {'places': ['pantry']}).is_accepted()
    assert not FleetNode.consider_patrol(fleet, {'places': [215]}).is_accepted()
    assert not FleetNode.consider_patrol(fleet, {'places': [True]}).is_accepted()


def test_only_matching_fleet_state_updates_the_robot(robot):
    fleet = SimpleNamespace(config={'fleet_name': 'HuskyA200'},
                            commands={'husky_0': robot})
    robot.last_graph_waypoint = 3
    FleetNode.observe_fleet_state(
        fleet, SimpleNamespace(name='other', robots=[SimpleNamespace(
            name='husky_0', task_id='wrong')]))
    assert robot.task_id is None
    FleetNode.observe_fleet_state(
        fleet, SimpleNamespace(name='HuskyA200', robots=[SimpleNamespace(
            name='husky_0', task_id='patrol-1')]))
    assert robot.task_id == 'patrol-1'
    assert robot.origin_waypoint == 3


def test_non_goal_problem_does_not_consume_nav2_failure_budget(robot):
    robot.last_graph_waypoint = 3
    robot.observe_task('patrol-1')
    robot.fail('Robot left graph merge tolerance')
    assert robot.failure_count == 0
    assert robot.update.replans == 1
    assert robot.update.kills == []
