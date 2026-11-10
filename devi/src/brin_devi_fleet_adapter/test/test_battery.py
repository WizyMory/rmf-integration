import time
from types import SimpleNamespace

from std_msgs.msg import Float32
from brin_devi_fleet_adapter.battery import BatteryTelemetry, voltage_soc
from brin_devi_fleet_adapter.preflight import Inspection
from brin_devi_fleet_adapter.adapter import DeviFleetNode


def test_devi_native_float32_measurement_and_calibrated_soc():
    observer = SimpleNamespace(battery_voltage=None, battery_observed_at=None)
    Inspection.observe_battery(observer, Float32(data=20.))
    assert observer.battery_voltage == 20.
    assert abs(time.monotonic()-observer.battery_observed_at) < 1.
    assert voltage_soc(observer.battery_voltage, 15., 25.) == .5
    telemetry = BatteryTelemetry('Devi', 'devi', '/battery', estimated=True)
    telemetry.observe(20., .5, observer.battery_observed_at)
    node = SimpleNamespace(battery=telemetry)
    assert DeviFleetNode.battery_soc(node, 'devi') == .5
    telemetry.observed_at -= 11.
    assert DeviFleetNode.battery_soc(node, 'devi') is None


def test_invalid_devi_sample_never_reuses_previous_measurement():
    observer = SimpleNamespace(battery_voltage=24., battery_observed_at=None)
    Inspection.observe_battery(observer, Float32(data=float('nan')))
    assert observer.battery_voltage is None
