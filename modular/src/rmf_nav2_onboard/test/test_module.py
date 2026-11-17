from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from rmf_nav2_onboard.cli import create_profile, options, task_payload
from rmf_nav2_onboard.config import Alignment, ConfigError, asset_hashes, distance_to_graph, environment, load
from rmf_nav2_onboard.controller import Controller
from rmf_nav2_onboard.gateway import Gateway
from rmf_nav2_onboard.render import nav2_fragment, service, transit_xml
from rmf_nav2_onboard.runtime import CORE, report


@pytest.fixture
def profile(tmp_path):
    create_profile(options(['new', '--name', 'robot_01', '--fleet', 'Robot01Fleet',
                            '--namespace', '/unit', '--output', str(tmp_path/'robot')]))
    path = tmp_path/'robot/robot.yaml'
    document = yaml.safe_load(path.read_text())
    document['geometry'] = {'footprint_radius': .4, 'vicinity_radius': .6}
    document['motion'].update(linear_speed=.3, linear_acceleration=.2,
                              angular_speed=.5, angular_acceleration=.4)
    document['rmf']['home_waypoint'] = 'home'
    document['rmf']['expected_profile_digest'] = 'a'*64
    vertices = [[0., 0., {'name': 'home', 'is_charger': True}], [3., 0., {'name': 'station'}]]
    graph = {'levels': {'L1': {'vertices': vertices, 'lanes': [[0, 1, {}], [1, 0, {}]]}}}
    (path.parent/'assets/nav_graph.yaml').write_text(yaml.safe_dump(graph))
    (path.parent/'assets/site.building.yaml').write_text('name: test_site\n')
    (path.parent/'assets/map.yaml').write_text('image: map.pgm\nresolution: 1.0\norigin: [0, 0, 0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196\n')
    (path.parent/'assets/map.pgm').write_bytes(b'P5\n3 3\n255\n'+bytes([254])*9)
    path.write_text(yaml.safe_dump(document))
    config = load(path, pinned=False)
    path.with_name('assets.lock.json').write_text(json.dumps(asset_hashes(config)))
    return path, config


def save(path, config):
    document = {k: v for k, v in config.items() if not k.startswith('_')}
    path.write_text(yaml.safe_dump(document))


def test_profile_is_portable_and_uncommissioned(profile):
    path, config = profile
    assert load(path)['nav2']['navigate_action'] == '/unit/navigate_to_pose'
    assert config['robot']['name'] == 'robot_01'
    assert config['nav2']['tf_topic'] == '/tf'
    with pytest.raises(ConfigError, match='Commissioning pending'):
        load(path, commissioned=True)
    with pytest.raises(FileExistsError):
        create_profile(options(['new', '--name', 'robot_01', '--fleet', 'Robot01Fleet', '--output', str(path.parent)]))


@pytest.mark.parametrize('section,key,value', [
    ('geometry', 'footprint_radius', None), ('geometry', 'footprint_radius', True),
    ('motion', 'linear_speed', float('nan')), ('nav2', 'domain_id', True),
    ('nav2', 'domain_id', 233), ('nav2', 'rmw', 'unknown'),
    ('nav2', 'map_frame', '/map'), ('nav2', 'planner_id', 'bad"xml'),
    ('nav2', 'max_data_age', -1), ('nav2', 'final_orientation_only', 'true'),
    ('motion', 'reversible', True), ('rmf', 'expected_profile_digest', None),
    ('alignment', 'yaw', float('inf'))])
def test_rejects_unmeasured_or_malformed_parameters(profile, section, key, value):
    path, config = profile
    config[section][key] = value
    save(path, config)
    with pytest.raises(ConfigError):
        load(path)


def test_asset_change_is_detected(profile):
    path, config = profile
    (path.parent/'assets/map.pgm').write_bytes(b'other image')
    with pytest.raises(ConfigError, match='lock mismatch'):
        load(path)


def test_alignment_roundtrip_and_lane_distance(profile):
    _, config = profile
    alignment = Alignment({'x': 2., 'y': -3., 'yaw': 1.2})
    assert alignment.to_nav2(alignment.to_rmf([4., -2., .4])) == pytest.approx([4., -2., .4])
    assert distance_to_graph(config, [1.5, .1, 0]) == pytest.approx(.1)
    assert distance_to_graph(config, [10, 0, 0]) == pytest.approx(7)


def test_explicit_dds_environment_does_not_inherit_other_domain(profile):
    _, config = profile
    env = environment({**config['nav2'], 'domain_id': 73})
    assert env['ROS_DOMAIN_ID'] == '73'
    assert env['ROS_DISCOVERY_SERVER'] == ''
    assert env['CYCLONEDDS_URI'] == ''


def test_readonly_gateway_cannot_command_even_if_a_caller_is_wrong():
    gateway = Gateway.__new__(Gateway)
    gateway.allow_commands = False
    gateway.connection = SimpleNamespace(send=lambda *_: pytest.fail('No command may cross the read-only boundary'))
    for operation in ('goal', 'cancel'):
        with pytest.raises(RuntimeError, match='Read-only'):
            gateway.send(operation)


def test_preflight_requires_core_profile_and_fresh_nav2(profile):
    _, config = profile
    state = {'nav2_ready': True, 'errors': [], 'pose': [1., 0., 0.]}
    assert report(config, state, 'a'*64, .1, list(CORE), 1)['accepted']
    assert not report(config, state, 'a'*64, 6., list(CORE), 1)['accepted']
    assert not report(config, state, 'b'*64, .1, list(CORE), 1)['accepted']
    assert not report(config, state, 'a'*64, .1, [*CORE, CORE[0]], 1)['accepted']
    assert not report(config, {**state, 'pose': [20., 20., 0.]}, 'a'*64, .1, list(CORE), 1)['accepted']


def test_task_dry_run_is_targeted_and_validates_waypoints(profile):
    _, config = profile
    args = options(['task', '--config', 'unused.yaml', '--places', 'station'])
    assert not args.send
    payload = task_payload(config, args)
    assert payload['type'] == 'robot_task_request'
    assert (payload['fleet'], payload['robot']) == ('Robot01Fleet', 'robot_01')
    args.places = ['missing']
    with pytest.raises(ConfigError, match='Unknown waypoint'):
        task_payload(config, args)


def test_transit_requires_confirmed_nav2_setup_and_renders_correct_client(profile):
    path, config = profile
    config['nav2'].update(final_orientation_only=True, transit_xy_tolerance=.2)
    save(path, config)
    with pytest.raises(ConfigError, match='transit parameters'):
        load(path)
    config['nav2']['transit_params_confirmed'] = True
    save(path, config)
    actual = load(path)
    fragment = yaml.safe_load(nav2_fragment(actual))
    assert fragment['/unit/bt_navigator_navigate_to_pose_rclcpp_node']['ros__parameters']['goal_reached_tol'] == .2
    assert 'robot_base_frame="base_link"' in transit_xml(actual)


def test_service_is_rendered_only_and_quotes_workspace(profile, tmp_path):
    _, config = profile
    workspace = tmp_path/'workspace with spaces'
    (workspace/'tools').mkdir(parents=True)
    (workspace/'tools/robot.bash').write_text('# placeholder')
    result = service(config, workspace)
    assert '--enable-dispatch' in result
    assert 'KillMode=mixed' in result
    assert f'"{workspace}/tools/robot.bash"' in result
    assert not (tmp_path/'service').exists()


@pytest.fixture
def machine(profile):
    _, config = profile
    config['nav2']['final_orientation_only'] = True
    messages, failures, replans, logs = [], [], [], []
    clock = [datetime(2026, 1, 1)]
    gateway = SimpleNamespace(send=lambda operation, **values: messages.append({'op': operation, **values}))
    controller = Controller(config, gateway, Alignment(config['alignment']), lambda: clock[0],
        logs.append, failures.append, lambda: replans.append(True), '/transit.xml')
    controller.task('task_1')
    controller.tick({'pose': [0., 0., 0.]})
    return controller, messages, failures, replans, clock


def waypoint(seconds=0, x=1.):
    return SimpleNamespace(position=[x, 0., 0.], time=datetime(2026, 1, 1)+timedelta(seconds=seconds), graph_index=1)


def accept(controller):
    events = [{'kind': 'accepted', 'id': controller.active, 'accepted': True}]
    controller.acknowledge(events)
    controller.tick({'pose': [0, 0, 0]}, events)


def test_transit_then_final_and_hold_until_reserved_time(machine):
    controller, messages, failures, replans, clock = machine
    done = []
    controller.follow([waypoint(10), waypoint(20, 2.)], lambda *_: None, lambda: done.append(True))
    controller.tick({'pose': [0, 0, 0]})
    assert messages[-1]['behavior_tree'] == '/transit.xml'
    accept(controller)
    controller.tick({'pose': [1, 0, 0]}, [{'kind': 'result', 'id': controller.active, 'status': 4}])
    assert len(messages) == 1 and not done
    clock[0] += timedelta(seconds=10)
    controller.tick({'pose': [1, 0, 0]})
    assert messages[-1]['behavior_tree'] == ''
    accept(controller)
    clock[0] += timedelta(seconds=10)
    controller.tick({'pose': [2, 0, 0]}, [{'kind': 'result', 'id': controller.active, 'status': 4}])
    assert done == [True] and not failures


def test_replacement_waits_for_old_result_even_after_late_acceptance(machine):
    controller, messages, *_ = machine
    old_done, new_done = [], []
    controller.follow([waypoint()], lambda *_: None, lambda: old_done.append(True))
    controller.tick({'pose': [0, 0, 0]})
    old = controller.active
    controller.follow([waypoint(x=3.)], lambda *_: None, lambda: new_done.append(True))
    controller.tick({'pose': [0, 0, 0]})
    assert messages[-1] == {'op': 'cancel', 'id': old}
    accept(controller)
    assert controller.active == old and len(messages) == 2
    controller.tick({'pose': [0, 0, 0]}, [{'kind': 'result', 'id': old, 'status': 5}])
    assert messages[-1]['op'] == 'goal' and controller.active != old
    assert not old_done and not new_done


def test_failure_or_readiness_loss_never_finishes_a_task(machine):
    controller, messages, failures, *_ = machine
    done = []
    controller.follow([waypoint()], lambda *_: None, lambda: done.append(True))
    controller.tick({'pose': [0, 0, 0]})
    accept(controller)
    controller.tick({}, ready=False)
    assert messages[-1]['op'] == 'cancel' and failures and not done
    controller.tick({'pose': [0, 0, 0]}, [{'kind': 'result', 'id': controller.active, 'status': 4}])
    assert not done  # A late successful result of a cancelled path is stale.


def test_idle_paths_do_not_dispatch_and_abort_does_not_report_success(machine):
    controller, messages, failures, *_ = machine
    controller.task('')
    controller.follow([waypoint()], lambda *_: None, lambda: pytest.fail('Idle path completed'))
    controller.tick({'pose': [0, 0, 0]})
    assert not messages
    controller.task('task_2')
    controller.follow([waypoint()], lambda *_: None, lambda: pytest.fail('Aborted goal completed'))
    controller.tick({'pose': [0, 0, 0]})
    controller.tick({'pose': [0, 0, 0]}, [{'kind': 'result', 'id': controller.active, 'status': 6}])
    assert failures


def test_feedback_updates_eta_only_for_the_owned_live_goal(machine):
    controller, messages, *_ = machine
    estimates = []
    controller.follow([waypoint()], lambda *values: estimates.append(values), lambda: None)
    controller.tick({'pose': [0, 0, 0]})
    accept(controller)
    controller.tick({'pose': [0, 0, 0]}, [
        {'kind': 'feedback', 'id': 'stale', 'remaining': 50.},
        {'kind': 'feedback', 'id': controller.active, 'remaining': 12.}])
    assert estimates[-1] == (0, timedelta(seconds=12))
    before = len(estimates)
    controller.stop()
    controller.tick({'pose': [0, 0, 0]}, [{'kind': 'feedback', 'id': controller.active, 'remaining': 100.}])
    assert len(estimates) == before


def test_graph_without_required_charger_fails_before_native_rmf_can_abort(profile):
    path, config = profile
    graph_file = Path(config['rmf']['nav_graph'])
    graph = yaml.safe_load(graph_file.read_text())
    graph['levels']['L1']['vertices'][0][2].pop('is_charger')
    graph_file.write_text(yaml.safe_dump(graph))
    with pytest.raises(ConfigError, match='is_charger'):
        load(path, pinned=False)
