from types import SimpleNamespace
import pickle
import os
import signal
import time

import pytest
from geometry_msgs.msg import Twist, PoseWithCovarianceStamped
from nav_msgs.msg import OccupancyGrid
from nav2_msgs.action import NavigateToPose

from brin_devi_fleet_adapter.gateway import Nav2Gateway, ActionProxy, StopProxy


@pytest.fixture
def gateway():
    gateway = Nav2Gateway.__new__(Nav2Gateway)
    incoming, outgoing = [], []
    gateway.connection = SimpleNamespace(send=outgoing.append,
        poll=lambda: bool(incoming), recv=lambda: incoming.pop(0))
    gateway.process = SimpleNamespace(is_alive=lambda: True)
    gateway.allow_commands = True
    gateway.pending, gateway.goals = {}, {}
    gateway.sequence = 0
    gateway.state = {'nav2_ready': True}
    gateway.received_at = time.monotonic()
    return gateway, incoming, outgoing


def test_pipe_preserves_acceptance_feedback_cancel_and_terminal_result(gateway):
    gateway, incoming, outgoing = gateway
    feedback = []
    proxy = ActionProxy(gateway)
    future = proxy.send_goal_async(NavigateToPose.Goal(), feedback.append)
    request_id = outgoing[0]['id']
    assert not future.done()
    incoming.append({'kind': 'accepted', 'id': request_id, 'accepted': True})
    gateway.poll()
    handle = future.result()
    assert handle.accepted
    incoming.append({'kind': 'feedback', 'id': request_id, 'value': 'actual-feedback'})
    gateway.poll()
    assert feedback == ['actual-feedback']
    cancellation = handle.cancel_goal_async()
    assert outgoing[-1]['op'] == 'cancel'
    assert outgoing[-1]['goal_id'] == request_id
    assert not cancellation.done()
    incoming.extend([
        {'kind': 'reply', 'id': outgoing[-1]['id'], 'value': 'cancel-ack'},
        {'kind': 'result', 'id': request_id, 'value': 'terminal-result'}])
    gateway.poll()
    assert cancellation.result() == 'cancel-ack'
    assert handle.get_result_async().result() == 'terminal-result'


def test_read_only_gateway_cannot_send_goals_cancels_or_velocity(gateway):
    gateway, _, outgoing = gateway
    gateway.allow_commands = False
    for operation in ('goal', 'cancel', 'stop'):
        with pytest.raises(RuntimeError, match='Read-only'):
            gateway.send({'op': operation})
    assert outgoing == []


def test_gateway_cannot_send_nonzero_motor_velocity(gateway):
    gateway, _, outgoing = gateway
    command = Twist()
    command.linear.x = 0.1
    with pytest.raises(ValueError, match='zero velocity'):
        StopProxy(gateway).publish(command)
    assert outgoing == []


def test_manual_pose_capability_does_not_allow_motion(gateway):
    gateway, _, outgoing = gateway
    gateway.allow_commands = False
    pose = PoseWithCovarianceStamped()
    with pytest.raises(RuntimeError, match='Manual initial pose'):
        gateway.send({'op': 'initial_pose', 'pose': pose})
    gateway.allow_initial_pose = True
    gateway.send({'op': 'initial_pose', 'pose': pose})
    for operation in ('goal', 'cancel', 'stop'):
        with pytest.raises(RuntimeError, match='Read-only'):
            gateway.send({'op': operation})
    assert outgoing == [{'op': 'initial_pose', 'pose': pose}]


def test_actual_map_crosses_pipe_without_changing_its_coordinates(gateway):
    gateway, incoming, _ = gateway
    message = OccupancyGrid()
    message.header.frame_id = 'map'
    message.info.origin.position.y = -33.65
    message.data = [0, 100, -1]
    incoming.append({'kind': 'map', 'value': pickle.loads(pickle.dumps(message))})
    gateway.poll()
    assert gateway.map_message == message


def test_stale_worker_state_prevents_navigation(gateway):
    gateway, _, _ = gateway
    gateway.received_at = time.monotonic() - 3.
    assert not ActionProxy(gateway).server_is_ready()


def test_actual_nav2_messages_can_cross_the_private_process_pipe():
    goal = NavigateToPose.Goal()
    goal.pose.header.frame_id = 'map'
    goal.pose.pose.position.x = -3.5
    assert pickle.loads(pickle.dumps(goal)) == goal


def test_queued_old_state_is_never_treated_as_fresh(gateway):
    gateway, incoming, _ = gateway
    incoming.append({'kind': 'state', 'state': {'nav2_ready': True},
                     'observed_at': time.monotonic() - 10.})
    gateway.poll()
    assert not ActionProxy(gateway).server_is_ready()


def test_worker_result_failure_reaches_the_accepted_goal(gateway):
    gateway, incoming, outgoing = gateway
    future = ActionProxy(gateway).send_goal_async(NavigateToPose.Goal())
    request_id = outgoing[0]['id']
    incoming.append({'kind': 'accepted', 'id': request_id, 'accepted': True})
    gateway.poll()
    result = future.result().get_result_async()
    incoming.append({'kind': 'error', 'id': request_id, 'error': 'Nav2 result unavailable'})
    gateway.poll()
    with pytest.raises(RuntimeError, match='Nav2 result unavailable'):
        result.result()


def test_repeated_sigint_during_close_does_not_interrupt_child_cleanup(gateway):
    gateway, _, outgoing = gateway
    closed = []
    gateway.closed = False
    gateway.connection.close = lambda: closed.append('pipe')
    gateway.process.is_alive = lambda: False
    gateway.process.join = lambda timeout: os.kill(os.getpid(), signal.SIGINT)
    previous = signal.getsignal(signal.SIGINT)
    gateway.close()
    gateway.close()
    assert outgoing == [{'op': 'close'}]
    assert closed == ['pipe']
    assert signal.getsignal(signal.SIGINT) == previous
