"""Offline guard/argument tests: never source ROS or contact a robot."""
from pathlib import Path
import importlib.util
import json
import os
import subprocess
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest


ROOT = Path(__file__).resolve().parents[1]


def run_tool(name, *arguments, **environment):
    command = ['bash'] if name.endswith('.bash') else [sys.executable]
    return subprocess.run(
        command + [str(ROOT / 'tools' / name), *arguments],
        env={**os.environ, **environment}, capture_output=True, text=True,
        timeout=5, check=False)


def test_shell_syntax():
    result = subprocess.run(
        ['bash', '-n', str(ROOT / 'tools/integration.bash')],
        capture_output=True, text=True, timeout=5, check=False)
    assert result.returncode == 0, result.stderr


def test_help_without_ros():
    assert run_tool('integration.bash', '--help').returncode == 0


@pytest.mark.parametrize('target,interface,peer', [
    ('laptop', 'wlp9s0', '192.168.0.120'),
    ('husky', 'wlp2s0', '192.168.0.218'),
])
def test_lan_profiles_select_only_the_target_wifi(target, interface, peer):
    profile = ET.parse(ROOT / target / 'src/brin_husky_distributed/config/cyclonedds_lan.xml')
    interfaces = profile.findall('./Domain/General/Interfaces/NetworkInterface')
    assert len(interfaces) == 1
    assert interfaces[0].attrib == {'name': interface}
    assert profile.find('./Domain/Discovery/Peers/Peer').attrib == {'Address': peer}
    assert profile.findtext('./Domain/General/AllowMulticast') == 'spdp'
    assert profile.findtext('./Domain/Discovery/ParticipantIndex') == 'auto'


@pytest.mark.parametrize('arguments', [
    ('husky', 'core'), ('laptop', 'preflight'), ('laptop', 'adapter'),
    ('husky', 'web'), ('bad', 'build'), ('laptop', 'build', '--merge-install'),
    ('husky', 'profile', 'start_nav2:=true'),
])
def test_reject_wrong_roles_and_build_flags(arguments):
    assert run_tool('integration.bash', *arguments).returncode == 2


def test_dispatch_locked_by_default():
    result = run_tool('integration.bash', 'husky', 'adapter', BRIN_ENABLE_DISPATCH='0')
    assert result.returncode == 2
    assert 'Refusing dispatch' in result.stderr


@pytest.mark.parametrize('argument', [
    'start_nav2:=true', 'start_hokuyo:=true', 'enable_dispatch:=true',
    'use_sim_time:=true',
])
def test_preflight_cannot_override_guard_options(argument):
    result = run_tool('integration.bash', 'husky', 'preflight', argument)
    assert result.returncode == 2
    assert 'Safety option' in result.stderr


@pytest.mark.parametrize('arguments', [
    ('--role', 'robot', '--session', '../cmd_vel'),
    ('--role', 'robot', '--session', 'valid', '--timeout', '0'),
    ('--role', 'laptop', '--session', 'valid', '--timeout', '61'),
])
def test_roundtrip_rejects_unbounded_or_unsafe_arguments(arguments):
    assert run_tool('dds_roundtrip.py', *arguments).returncode == 2


def test_native_check_rejects_other_domain():
    result = run_tool('native_adapter_check.py', ROS_DOMAIN_ID='42')
    assert result.returncode == 2
    assert 'ROS_DOMAIN_ID=0' in result.stderr


@pytest.mark.parametrize('wait', ['0', '61'])
def test_native_check_bounded_wait(wait):
    assert run_tool('native_adapter_check.py', '--wait', wait).returncode == 2


@pytest.mark.parametrize('connected', [False, True])
def test_native_probe_does_not_start_background_executor(monkeypatch, capsys, connected):
    specification = importlib.util.spec_from_file_location(
        'native_link_probe', ROOT / 'tools/native_adapter_check.py')
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    events = []

    class DiagnosticAdapter:
        def start(self):
            raise AssertionError('diagnostic must not start an adapter executor')

        def stop(self):
            raise AssertionError('diagnostic must not stop an adapter executor')

        def __del__(self):
            events.append('released')

    def make(name, wait_time):
        assert name == 'husky_rmf_link_check'
        assert wait_time.total_seconds() == 12.0
        return DiagnosticAdapter() if connected else None

    monkeypatch.setitem(sys.modules, 'rmf_adapter', SimpleNamespace(
        init_rclcpp=lambda: None, Adapter=SimpleNamespace(make=make)))
    monkeypatch.setitem(sys.modules, 'rmf_fleet_msgs', SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'rmf_task_msgs', SimpleNamespace())
    monkeypatch.setenv('ROS_DOMAIN_ID', '0')
    monkeypatch.setattr(sys, 'argv', ['native_adapter_check.py'])
    assert module.main() == (0 if connected else 2)
    result = json.loads(capsys.readouterr().out)
    assert result['native_adapter_connected_to_schedule'] == connected
    assert result['robot_registered'] is False
    assert events == (['released'] if connected else [])
