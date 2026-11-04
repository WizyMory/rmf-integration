"""Task API protocol checks without creating ROS participants or commanding robots."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from rmf_task_msgs.msg import ApiRequest, ApiResponse, Assignment, DispatchState, DispatchStates
from rclpy.serialization import deserialize_message, serialize_message

from brin_husky_distributed import task_client as client


TARGETS = {'husky_0': 'HuskyA200', 'devi': 'Devi'}
PACKAGE = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('robot,fleet', [('husky_0', 'HuskyA200'), ('devi', 'Devi')])
def test_explicit_robot_is_routed_to_its_actual_fleet(robot, fleet):
    payload = client.make_payload(TARGETS, ['ws_p1'], robot=robot, now_ns=123_000_000)
    assert payload == {'type': 'robot_task_request', 'fleet': fleet, 'robot': robot,
        'request': {'category': 'patrol', 'description': {'places': ['ws_p1'], 'rounds': 1},
                    'unix_millis_earliest_start_time': 123}}


def test_native_bidding_has_no_preset_robot_or_fleet():
    payload = client.make_payload(TARGETS, ['ws_p1', 'ws_p2'], bid=True, rounds=2)
    assert payload['type'] == 'dispatch_task_request'
    assert 'fleet' not in payload and 'robot' not in payload
    assert payload['request']['description'] == {'places': ['ws_p1', 'ws_p2'], 'rounds': 2}


def test_cancel_uses_booking_id_without_a_robot_selector():
    assert client.make_payload(TARGETS, cancel='patrol.dispatch-9') == {
        'type': 'cancel_task_request', 'task_id': 'patrol.dispatch-9',
        'labels': ['BRIN laptop task console cancellation']}


@pytest.mark.parametrize('args', [
    ['--robot', 'devi', '--bid', '--places', 'ws_p1'],
    ['--robot', 'devi'], ['--places', 'ws_p1'], ['--bid'],
    ['--cancel', 'x', '--places', 'ws_p1'], ['--robot', ''], ['--cancel', ' '],
    ['--bid', '--places', 'ws_p1', '--rounds', '0'],
    ['--bid', '--places', 'ws_p1', '--timeout', 'nan'],
    ['--bid', '--places', 'ws_p1', '--timeout', '121'],
    ['--interactive', '--dry-run'],
])
def test_ambiguous_or_incomplete_commands_are_rejected(args):
    with pytest.raises(SystemExit) as error:
        client.parse_options(args)
    assert error.value.code == 2


def test_no_arguments_opens_interactive_console():
    assert client.parse_options([]).interactive


def test_unknown_targets_and_waypoints_are_rejected_before_ros():
    with pytest.raises(ValueError, match='Unknown robot'):
        client.make_payload(TARGETS, ['ws_p1'], robot='another_robot')
    with pytest.raises(ValueError, match='Unknown waypoint'):
        client.validate_places(['missing'], {'ws_p1': ('L1', [0., 1.])})
    assert client.load_targets(PACKAGE/'config/task_targets.yaml') == TARGETS


@pytest.mark.parametrize('document', ['', 'robots: null', 'robots: []', 'robots: {devi: 12}'])
def test_invalid_target_catalog_is_rejected(tmp_path, document):
    path = tmp_path/'targets.yaml'
    path.write_text(document)
    with pytest.raises(ValueError):
        client.load_targets(path)


def test_booking_id_is_distinct_from_api_request_id():
    assert client.booking_id({'success': True, 'state': {'booking': {'id': 'patrol-123'}}}) == 'patrol-123'
    assert client.booking_id({'request_id': 'api-123'}) is None
    assert client.booking_id({'state': {'booking': {'id': 123}}}) is None


@pytest.fixture
def node():
    node = client.TaskClient.__new__(client.TaskClient)
    node.profile, node.targets = {'digest': 'profile-a'}, TARGETS
    node.profile_digest, node.profile_seen_at = 'profile-a', client.time.monotonic()
    node.fleets = {'Devi': (client.time.monotonic(), {'devi'})}
    node.responses, node.dispatches = {}, {}
    node.pending_id = None
    node.request_publisher = SimpleNamespace(get_subscription_count=lambda: 1, publish=Mock())
    node.sent_publisher = node.request_publisher
    node.request_qos = object()
    node.create_publisher = Mock(return_value=node.sent_publisher)
    node.destroy_publisher = Mock()
    return node


def test_response_correlation_ignores_acknowledgements_and_other_clients(node):
    node.pending_id = 'ours'
    node.receive_response(ApiResponse(request_id='other', type=ApiResponse.TYPE_RESPONDING,
                                      json_msg='{"success": true}'))
    assert node.responses == {}
    node.receive_response(ApiResponse(request_id='ours', type=ApiResponse.TYPE_ACKNOWLEDGE,
                                      json_msg='{"success": true}'))
    assert node.responses == {}
    node.receive_response(ApiResponse(request_id='ours', type=ApiResponse.TYPE_RESPONDING,
                                      json_msg='{"success": false, "errors": ["no bid"]}'))
    assert node.responses['ours']['success'] is False


@pytest.mark.parametrize('text', ['broken-json', '[]', '{}', '{"success": "false"}'])
def test_malformed_correlated_response_never_looks_successful(node, text):
    node.pending_id = 'ours'
    node.receive_response(ApiResponse(request_id='ours', type=ApiResponse.TYPE_RESPONDING, json_msg=text))
    assert node.responses['ours']['success'] is False


def test_profile_mismatch_and_missing_robot_block_publication(node):
    payload = client.make_payload(TARGETS, ['ws_p1'], robot='devi')
    node.profile_digest = 'another-map'
    assert 'profile' in node.readiness_error(payload)
    node.profile_digest = 'profile-a'
    node.fleets.clear()
    assert 'Target robot' in node.readiness_error(payload)
    assert node.request_publisher.publish.call_count == 0


def test_bidding_result_requires_dispatch_acknowledgement_and_assignment():
    assignment = Assignment(is_assigned=True, fleet_name='Devi', expected_robot_name='devi')
    assert client.dispatch_result(DispatchState(status=DispatchState.STATUS_SELECTED, assignment=assignment)) is None
    result = client.dispatch_result(DispatchState(status=DispatchState.STATUS_DISPATCHED, assignment=assignment))
    assert result == {'success': True, 'dispatch_status': 'dispatched', 'fleet': 'Devi', 'robot': 'devi'}
    assert not client.dispatch_result(DispatchState(status=DispatchState.STATUS_DISPATCHED))['success']
    assert not client.dispatch_result(DispatchState(status=DispatchState.STATUS_FAILED_TO_ASSIGN))['success']


@pytest.mark.parametrize('status,code', [(DispatchState.STATUS_DISPATCHED, 0),
                                        (DispatchState.STATUS_FAILED_TO_ASSIGN, 1)])
def test_api_acceptance_waits_for_actual_bidding_outcome(node, monkeypatch, status, code):
    monkeypatch.setattr(client.rclpy, 'ok', lambda: True)
    events = []

    def spin(_node, timeout_sec):
        if not events:
            node.receive_response(ApiResponse(request_id=node.pending_id, type=ApiResponse.TYPE_RESPONDING,
                json_msg=json.dumps({'success': True, 'state': {'booking': {'id': 'patrol-7'}}})))
        else:
            node.receive_dispatch(DispatchStates(finished=[DispatchState(task_id='patrol-7', status=status,
                assignment=Assignment(is_assigned=True, fleet_name='Devi', expected_robot_name='devi'),
                errors=[] if code == 0 else ['No fleet offered a bid'])]))
        events.append(True)

    monkeypatch.setattr(client.rclpy, 'spin_once', spin)
    result, actual_code = node.transact(client.make_payload(TARGETS, ['ws_p1'], bid=True), 5.)
    assert actual_code == code
    assert result['task_id'] == 'patrol-7' and result['task_completed'] is False
    assert result['allocation']['success'] == (code == 0)
    assert len(events) >= 2 and node.sent_publisher.publish.call_count == 1
    sent = node.sent_publisher.publish.call_args.args[0]
    assert deserialize_message(serialize_message(sent), ApiRequest).request_id == node.pending_id
    node.destroy_publisher.assert_called_once_with(node.sent_publisher)
    assert node.request_publisher is None  # No retained request history between menu commands.


def test_response_timeout_does_not_resubmit_or_claim_rejection(node, monkeypatch):
    clock = [0.]
    monkeypatch.setattr(client.rclpy, 'ok', lambda: True)
    monkeypatch.setattr(client.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(node, 'readiness_error', lambda payload: None)
    monkeypatch.setattr(client.rclpy, 'spin_once', lambda *a, **kw: clock.__setitem__(0, clock[0] + 1.))
    with pytest.raises(RuntimeError, match='outcome is unknown'):
        node.transact(client.make_payload(TARGETS, ['ws_p1'], robot='devi'), 2.)
    assert node.sent_publisher.publish.call_count == 1
    node.destroy_publisher.assert_called_once_with(node.sent_publisher)


def test_read_only_modes_never_initialize_ros(monkeypatch, capsys):
    monkeypatch.setattr(client, 'profile_info', lambda name: {
        'name': name, 'digest': 'digest', 'places': {'L1': {'ws_p1': [1., 2.]}}})
    monkeypatch.setattr(client, 'load_targets', lambda: TARGETS)
    monkeypatch.setattr(client.rclpy, 'init', Mock(side_effect=AssertionError('must not create ROS context')))
    assert client.main(['--robot', 'devi', '--places', 'ws_p1', '--dry-run']) == 0
    assert json.loads(capsys.readouterr().out)['request_published'] is False
    assert client.main(['--list-waypoints']) == 0
    assert 'ws_p1' in capsys.readouterr().out


def test_cancellation_does_not_require_a_map_or_target_catalog(monkeypatch, capsys):
    monkeypatch.setattr(client, 'profile_info', Mock(side_effect=AssertionError('cancel needs no map')))
    monkeypatch.setattr(client, 'load_targets', Mock(side_effect=AssertionError('cancel needs no catalog')))
    assert client.main(['--cancel', 'patrol-3', '--dry-run']) == 0
    assert json.loads(capsys.readouterr().out)['payload']['task_id'] == 'patrol-3'


@pytest.mark.parametrize('mode,schema_name', [
    ({'robot': 'devi', 'places': ['ws_p1']}, 'robot_task_request'),
    ({'bid': True, 'places': ['ws_p1']}, 'dispatch_task_request'),
    ({'cancel': 'patrol-3'}, 'cancel_task_request'),
])
def test_payloads_match_installed_rmf_api_schemas(mode, schema_name):
    import jsonschema
    from rmf_api_msgs import schemas
    definitions = {name: json.loads(getattr(schemas, name)()) for name in (
        'task_request', 'robot_task_request', 'dispatch_task_request', 'cancel_task_request')}
    schema = definitions[schema_name]
    resolver = jsonschema.RefResolver.from_schema(schema, store={
        item['$id']: item for item in definitions.values()})
    # These request schemas use ordinary object/array/string constraints;
    # Draft7 validates them with Humble's packaged jsonschema version.
    jsonschema.Draft7Validator(schema, resolver=resolver).validate(client.make_payload(TARGETS, **mode))


def test_api_acceptance_without_bidding_result_is_pending_not_success(node, monkeypatch):
    clock = [0.]
    monkeypatch.setattr(client.rclpy, 'ok', lambda: True)
    monkeypatch.setattr(client.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(node, 'readiness_error', lambda payload: None)

    def spin(*args, **kwargs):
        clock[0] += 1.
        if node.pending_id not in node.responses:
            node.receive_response(ApiResponse(request_id=node.pending_id, type=ApiResponse.TYPE_RESPONDING,
                json_msg='{"success": true, "state": {"booking": {"id": "patrol-8"}}}'))

    monkeypatch.setattr(client.rclpy, 'spin_once', spin)
    result, code = node.transact(client.make_payload(TARGETS, ['ws_p1'], bid=True), 3.)
    assert code == 2
    assert result['task_id'] == 'patrol-8' and result['assignment_pending'] is True
    assert result['allocation'] is None
    assert node.sent_publisher.publish.call_count == 1


def test_no_request_is_published_when_readiness_never_passes(node, monkeypatch):
    clock = [0.]
    monkeypatch.setattr(client.rclpy, 'ok', lambda: True)
    monkeypatch.setattr(client.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(node, 'readiness_error', lambda payload: 'Target robot not registered')
    monkeypatch.setattr(client.rclpy, 'spin_once', lambda *a, **kw: clock.__setitem__(0, clock[0] + 1.))
    with pytest.raises(RuntimeError, match='no request was published'):
        node.transact(client.make_payload(TARGETS, ['ws_p1'], robot='devi'), 2.)
    node.sent_publisher.publish.assert_not_called()
    node.destroy_publisher.assert_called_once_with(node.sent_publisher)


def test_interactive_decline_does_not_send_and_bid_uses_native_payload(node, monkeypatch):
    monkeypatch.setattr(client.rclpy, 'ok', lambda: True)
    answers = iter(['devi', 'ws_p1', 'n', 'bid', '1', 'y', 'q'])
    monkeypatch.setattr(client, 'prompt', lambda *args: next(answers))
    node.transact = Mock(return_value=({'task_id': 'patrol-9'}, 0))
    assert client.interactive(node, SimpleNamespace(rounds=1, timeout=30.), {'ws_p1': ('L1', [0., 1.])}) == 0
    node.transact.assert_called_once()
    payload, timeout = node.transact.call_args.args
    assert payload['type'] == 'dispatch_task_request' and 'robot' not in payload
    assert payload['request']['description']['places'] == ['ws_p1'] and timeout == 30.
