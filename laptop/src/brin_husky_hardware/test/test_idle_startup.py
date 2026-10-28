"""Offline checks for idle startup, task/path ordering and cancellation."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from brin_husky_hardware.adapter import HardwareCommand, HardwareFleetNode
from brin_husky_fleet_adapter.adapter import FleetNode

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    'idle_guard_test_helpers', ROOT / 'brin_husky_fleet_adapter/test/test_command.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
robot = helpers.robot


@pytest.fixture
def physical(robot):
    command = HardwareCommand(robot.node, robot.name, robot.adapter, robot.config)
    command.pose = [0.0, 0.0, 0.0]
    command.navigation_ready = True
    command.update = robot.update
    return command


def test_idle_registration_paths_never_send_goals_or_report_arrival(physical):
    finished = []
    for _ in range(3):
        physical.follow_new_path([helpers.waypoint()], lambda *args: None,
                                 lambda: finished.append(True))
        physical.tick()
    assert not physical.client.requests and not physical.backup_client.requests
    assert not finished and not physical.path


def test_late_task_identity_requires_a_new_path_not_an_idle_path(physical):
    physical.follow_new_path([helpers.waypoint()], lambda *args: None, lambda: None)
    physical.observe_task('patrol-1')
    physical.tick()
    assert physical.update.replans == 1
    assert not physical.client.requests
    physical.follow_new_path([helpers.waypoint()], lambda *args: None, lambda: None)
    physical.tick()
    assert len(physical.client.requests) == 1


def test_registration_disables_responsive_wait_before_exposing_update(monkeypatch, physical):
    calls = []
    update = SimpleNamespace(enable_responsive_wait=lambda value: calls.append(('wait', value)))
    monkeypatch.setattr(FleetNode, 'registered', lambda *args: calls.append(('registered',)))
    monkeypatch.setattr(HardwareFleetNode, 'get_logger',
                        lambda self: SimpleNamespace(info=lambda text: None))
    node = object.__new__(HardwareFleetNode)
    node.registered('husky_0', update)
    assert calls == [('wait', False), ('registered',)]


def test_task_end_cancels_an_active_goal(physical):
    physical.observe_task('patrol-1')
    physical.follow_new_path([helpers.waypoint()], lambda *args: None, lambda: None)
    physical.tick()
    goal = helpers.Goal()
    physical.client.requests[-1][1].set_result(goal)
    physical.observe_task(None)
    physical.tick()
    assert goal.cancellations == 1 and not physical.path
    physical.follow_new_path([helpers.waypoint()], lambda *args: None, lambda: None)
    physical.tick()
    assert len(physical.client.requests) == 1


def test_task_switch_discards_paths_from_previous_task(physical):
    physical.observe_task('patrol-1')
    physical.follow_new_path([helpers.waypoint()], lambda *args: None, lambda: None)
    physical.observe_task('patrol-2')
    physical.tick()
    assert not physical.client.requests
    assert physical.update.replans == 2
    physical.follow_new_path([helpers.waypoint()], lambda *args: None, lambda: None)
    physical.tick()
    assert len(physical.client.requests) == 1


def test_repeated_task_state_does_not_restart_navigation(physical):
    physical.observe_task('patrol-1')
    physical.follow_new_path([helpers.waypoint()], lambda *args: None, lambda: None)
    physical.tick()
    physical.observe_task('patrol-1')
    physical.tick()
    assert physical.update.replans == 1 and len(physical.client.requests) == 1
