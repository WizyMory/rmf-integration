"""Optional telemetry uses the installed native RMF API."""
from unittest.mock import Mock
from pathlib import Path
import pytest
from brin_devi_fleet_adapter.web import add_fleet, configured_server_uri, validate_server_uri


@pytest.mark.parametrize('uri', ['', 'ws://localhost:8000/_internal'])
def test_add_fleet_optional_uri(uri):
    native = Mock()
    traits, graph = object(), object()
    result = add_fleet(native, 'Devi', traits, graph, uri)
    args = ('Devi', traits, graph) + ((uri,) if uri else ())
    native.add_fleet.assert_called_once_with(*args)
    assert result is native.add_fleet.return_value


@pytest.mark.parametrize('uri', ['', 'ws://192.168.0.218:8000/_internal', 'wss://rmf-laptop.local/_internal'])
def test_robot_web_endpoint_accepts_laptop_or_disabled_mode(uri):
    assert validate_server_uri(uri) == uri


@pytest.mark.parametrize('uri', [None, True, 'http://192.168.0.218:8000/_internal',
    'ws://localhost:8000/_internal', 'ws://127.0.0.1:8000/_internal',
    'ws://[::1]:8000/_internal', 'ws://0.0.0.0:8000/_internal',
    'ws://[::ffff:127.0.0.1]:8000/_internal', 'ws://192.168.0.218:0/_internal',
    'ws://192.168.0.218:abc/_internal', 'ws://user:password@192.168.0.218/_internal',
    'ws://192.168.0.218:8000/_internal#fragment'])
def test_robot_web_endpoint_rejects_invalid_or_local_addresses(uri):
    with pytest.raises(ValueError):
        validate_server_uri(uri)


def test_boot_endpoint_is_read_from_config_and_can_be_disabled(tmp_path):
    package = Path(__file__).resolve().parents[1]
    assert configured_server_uri(package) == 'ws://192.168.0.218:8000/_internal'
    (tmp_path/'config').mkdir()
    path = tmp_path/'config/bringup.yaml'
    path.write_text('server_uri: ""\n')
    assert configured_server_uri(tmp_path) == ''
    path.write_text('traffic_profile: gedungWS_0\n')
    assert configured_server_uri(tmp_path) == ''
