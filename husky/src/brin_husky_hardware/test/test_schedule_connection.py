from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from brin_husky_hardware import adapter as hardware


def test_schedule_failure_is_bounded_and_allows_wireless_discovery(monkeypatch):
    config = yaml.safe_load((Path(__file__).resolve().parents[2]
                             / 'brin_husky_distributed/config/fleet_config.yaml').read_text())
    waits = []

    def unavailable(name, wait_time):
        waits.append(wait_time.total_seconds())
        return None

    monkeypatch.setattr(hardware, 'rmf', SimpleNamespace(
        Adapter=SimpleNamespace(make=unavailable)))
    monkeypatch.setattr(hardware, 'graph', SimpleNamespace(parse_graph=lambda *a: None))
    monkeypatch.setattr(hardware.rclpy, 'spin_once', lambda *a, **kw: None)
    parameters = {'use_sim_time': False, 'robots': ['husky_0'], 'nav_graph': 'unused'}
    node = SimpleNamespace(
        config=config, get_parameter=lambda name: SimpleNamespace(value=parameters[name]),
        get_logger=lambda: SimpleNamespace(warning=lambda text: None))
    with pytest.raises(RuntimeError, match='after 6 attempts'):
        hardware.HardwareFleetNode.start(node)
    assert waits == [15.0] * 6
    assert node.adapter is None


def test_hardware_initializes_cpp_before_python_context(monkeypatch):
    events = []
    monkeypatch.setattr(hardware.rmf, 'init_rclcpp', lambda: events.append('cpp'))
    monkeypatch.setattr(hardware.rclpy, 'init', lambda **kw: events.append('python'))
    monkeypatch.setattr(hardware.rclpy, 'spin', lambda node: None)
    monkeypatch.setattr(hardware.rclpy, 'ok', lambda: False)
    node = SimpleNamespace(commands={}, adapter=None, start=lambda: events.append('start'),
                           destroy_node=lambda: events.append('destroy'))
    monkeypatch.setattr(hardware, 'HardwareFleetNode', lambda: node)
    hardware.main()
    assert events == ['cpp', 'python', 'start', 'destroy']
