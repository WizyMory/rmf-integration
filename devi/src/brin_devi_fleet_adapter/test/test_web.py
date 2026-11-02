"""Optional telemetry uses the installed native RMF API."""
from unittest.mock import Mock
import pytest
from brin_devi_fleet_adapter.web import add_fleet


@pytest.mark.parametrize('uri', ['', 'ws://localhost:8000/_internal'])
def test_add_fleet_optional_uri(uri):
    native = Mock()
    traits, graph = object(), object()
    result = add_fleet(native, 'Devi', traits, graph, uri)
    args = ('Devi', traits, graph) + ((uri,) if uri else ())
    native.add_fleet.assert_called_once_with(*args)
    assert result is native.add_fleet.return_value
