import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from brin_devi_fleet_adapter.geometry import MapAlignment, require_commissioning
from brin_devi_fleet_adapter.profiles import load_settings, resolve_profile
from brin_devi_fleet_adapter.adapter import DeviCommand, main


SHARE = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('yaw', [0., math.pi/2, -2.3])
def test_round_trip_coordinate_alignment(yaw):
    alignment = MapAlignment({'confirmed': True, 'x': 4., 'y': -9., 'yaw': yaw})
    pose = [1.2, -3.4, 0.2]
    assert alignment.to_nav2(alignment.to_rmf(pose)) == pytest.approx(pose)


def test_alignment_rotates_goals_and_positions_in_opposite_directions():
    alignment = MapAlignment({'confirmed': True, 'x': 10., 'y': 20., 'yaw': math.pi/2})
    assert alignment.to_rmf([1., 0., 0.]) == pytest.approx([10., 21., math.pi/2])
    assert alignment.to_nav2([10., 21., math.pi/2]) == pytest.approx([1., 0., 0.])


@pytest.mark.parametrize('value', [None, float('nan'), float('inf'), True, '1.0'])
def test_reject_unknown_or_invalid_alignment(value):
    with pytest.raises(ValueError):
        MapAlignment({'confirmed': True, 'x': value, 'y': 0., 'yaw': 0.})


def test_shipped_config_never_authorizes_dispatch():
    settings = load_settings(SHARE/'config/devi.yaml')
    with pytest.raises(ValueError, match='alignment'):
        require_commissioning(settings)
    settings['map_alignment'] = {'confirmed': True, 'x': 0., 'y': 0., 'yaw': 0.}
    with pytest.raises(ValueError, match='footprint_confirmed'):
        require_commissioning(settings)


def test_direct_adapter_entry_rejects_dispatch_before_ros_init(monkeypatch):
    monkeypatch.setenv('ROS_DOMAIN_ID', '0')
    monkeypatch.delenv('BRIN_ENABLE_DISPATCH', raising=False)
    with pytest.raises(ValueError, match='BRIN_ENABLE_DISPATCH'):
        main()


def test_physical_recovery_never_starts_backup():
    reasons = []
    DeviCommand._start_escape(SimpleNamespace(_recovery_failed=reasons.append))
    assert len(reasons) == 1
    assert 'automatic reverse disabled' in reasons[0]


def test_idle_native_path_cannot_dispatch_without_task():
    fake = SimpleNamespace(task_id=None, node=SimpleNamespace(
        get_logger=lambda: SimpleNamespace(warning=lambda message: None)))
    DeviCommand.follow_new_path(fake, [], None, None)


def test_profile_digest_matches_original_laptop_bundle():
    import hashlib
    root = SHARE.parents[2]
    original = root/'laptop/src/brin_rmf_maps'
    if not original.exists():
        pytest.skip('laptop source not included in this deployment')
    digest = hashlib.sha256(b'gedungWS_0')
    for name in ('maps/gedungWS_0_rmf.building.yaml', 'nav_graphs/gedungWS_0.yaml',
                 'maps/gedungWS_0_rmf.yaml', 'maps/gedungWS_0.pgm',
                 'maps/gedungWS_0_fleet.yaml'):
        path = original/name
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    assert resolve_profile(SHARE)['digest'] == digest.hexdigest()


def test_preflight_retries_unanswered_read_only_lifecycle_query(monkeypatch):
    from concurrent.futures import Future
    from brin_devi_fleet_adapter import preflight
    unanswered, retried = Future(), Future()
    requests = []
    client = SimpleNamespace(service_is_ready=lambda: True,
        call_async=lambda request: (requests.append(request), retried)[1])
    state = {'client': client, 'future': unanswered, 'sent_at': 0., 'observed': None}
    fake = SimpleNamespace(lifecycle={'bt_navigator': state},
                           rmf=SimpleNamespace(spin_once=lambda: None))
    monkeypatch.setattr(preflight.rclpy, 'spin_once', lambda *a, **kw: None)
    monkeypatch.setattr(preflight.time, 'monotonic', lambda: 5.)
    preflight.Inspection.poll(fake)
    assert unanswered.cancelled()
    assert state['future'] is retried
    assert len(requests) == 1
    assert isinstance(requests[0], preflight.GetState.Request)
