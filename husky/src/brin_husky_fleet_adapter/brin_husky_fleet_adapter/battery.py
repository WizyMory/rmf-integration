"""Battery telemetry independent of ROS, with explicit freshness and no fake SOC."""
import math
import time


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def voltage_soc(voltage, empty, full):
    if not all(finite(v) for v in (voltage, empty, full)) or full <= empty:
        raise ValueError('Battery voltage calibration requires finite empty < full')
    if voltage <= 0:
        return None
    return max(0., min(1., (voltage - empty) / (full - empty)))


class BatteryTelemetry:
    def __init__(self, fleet, robot, source, estimated=False, max_age=10.):
        self.fleet, self.robot, self.source = fleet, robot, source
        self.estimated, self.max_age = estimated, max_age
        self.voltage = self.soc = None
        self.observed_at = None

    def observe(self, voltage, soc, observed_at=None):
        self.voltage = float(voltage) if finite(voltage) and voltage > 0 else None
        self.soc = float(soc) if finite(soc) and 0 <= soc <= 1 else None
        self.observed_at = time.monotonic() if observed_at is None else observed_at

    def snapshot(self, now=None):
        now = time.monotonic() if now is None else now
        age = max(0., now-self.observed_at) if self.observed_at is not None else None
        fresh = age is not None and age <= self.max_age
        return dict(fleet=self.fleet, robot=self.robot, source=self.source,
                    voltage=self.voltage if fresh else None,
                    soc=self.soc if fresh else None, estimated=self.estimated,
                    age_seconds=age, stale=not fresh,
                    unix_millis_time=round(time.time()*1000))
