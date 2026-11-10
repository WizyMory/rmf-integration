"""Battery calculations and HTTP cache behavior; no robot or ROS connection."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


BATTERY = [ROOT / f'{role}/src/{package}/{package}/battery.py' for role, package in (
    ('laptop', 'brin_husky_fleet_adapter'), ('husky', 'brin_husky_fleet_adapter'),
    ('devi', 'brin_devi_fleet_adapter'))]


@pytest.mark.parametrize('path', BATTERY)
def test_devi_calibration_and_clamping(path):
    battery = module(path)
    assert battery.voltage_soc(15., 15., 25.) == 0.
    assert battery.voltage_soc(20., 15., 25.) == .5
    assert battery.voltage_soc(25., 15., 25.) == 1.
    assert battery.voltage_soc(26., 15., 25.) == 1.
    assert battery.voltage_soc(14., 15., 25.) == 0.
    assert battery.voltage_soc(0., 15., 25.) is None
    with pytest.raises(ValueError):
        battery.voltage_soc(float('nan'), 15., 25.)
    with pytest.raises(ValueError):
        battery.voltage_soc(20., 25., 15.)


@pytest.mark.parametrize('path', BATTERY)
def test_unknown_invalid_zero_and_stale_soc(path):
    telemetry = module(path).BatteryTelemetry('fleet', 'robot', '/battery')
    assert telemetry.snapshot(now=100)['soc'] is None
    telemetry.observe(23.8, .197, observed_at=100.)
    assert telemetry.snapshot(now=105.)['soc'] == .197
    assert telemetry.snapshot(now=111.)['soc'] is None
    telemetry.observe(15., 0., observed_at=112.)
    assert telemetry.snapshot(now=112.)['soc'] == 0.
    telemetry.observe(float('nan'), float('nan'), observed_at=113.)
    assert telemetry.snapshot(now=113.)['soc'] is None
    json.dumps(telemetry.snapshot(now=113.), allow_nan=False)
    telemetry.observe(24., 95., observed_at=114.)
    assert telemetry.snapshot(now=114.)['soc'] is None


def test_http_cache_ages_even_when_publisher_stops(monkeypatch):
    m = module(ROOT/'main/web/battery_store.py')
    now = [100.]
    monkeypatch.setattr(m.time, 'monotonic', lambda: now[0])
    store = m.BatteryStore()
    sample = dict(fleet='Devi', robot='devi', source='/battery', soc=0., voltage=15.,
                  age_seconds=1., stale=False)
    store.receive(json.dumps(sample))
    assert store.snapshot()['robots'][0]['soc'] == 0.
    now[0] = 111.
    assert store.snapshot()['robots'][0]['stale']
    assert store.snapshot()['robots'][0]['voltage'] is None


@pytest.mark.parametrize('payload', ['null', '[]', '{}', 'broken',
    '{"fleet":"x","robot":"x","source":"x","soc":NaN}',
    '{"fleet":"x","robot":"x","source":"x","soc":4}'])
def test_http_cache_rejects_malformed_data(payload):
    store = module(ROOT/'main/web/battery_store.py').BatteryStore()
    store.receive(payload)
    assert store.snapshot()['robots'] == []
