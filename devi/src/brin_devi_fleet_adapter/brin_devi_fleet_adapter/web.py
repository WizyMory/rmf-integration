"""Optional RMF telemetry connection; task/control behavior stays in RMF."""
import ipaddress
from pathlib import Path
from urllib.parse import urlsplit

import yaml


def validate_server_uri(uri):
    if not isinstance(uri, str):
        raise ValueError('Devi server_uri must be a string')
    if not uri:
        return ''
    try:
        parsed = urlsplit(uri)
        port = parsed.port
    except ValueError as error:
        raise ValueError('Invalid Devi Web server_uri') from error
    if (parsed.scheme not in ('ws', 'wss') or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.fragment or port == 0):
        raise ValueError('Devi server_uri requires a ws:// or wss:// endpoint without credentials')
    host = parsed.hostname.lower().rstrip('.')
    local = host == 'localhost' or host.endswith('.localhost')
    try:
        address = ipaddress.ip_address(host)
        local = local or address.is_loopback or address.is_unspecified
        if address.version == 6 and address.ipv4_mapped:
            local = local or address.ipv4_mapped.is_loopback or address.ipv4_mapped.is_unspecified
    except ValueError:
        pass  # A LAN hostname is resolved by the robot at runtime.
    if local:
        raise ValueError('Devi server_uri must use the laptop LAN address, not localhost')
    return uri


def configured_server_uri(share):
    settings = yaml.safe_load((Path(share)/'config/bringup.yaml').read_text())
    return validate_server_uri(settings.get('server_uri', ''))


def add_fleet(adapter, fleet_name, traits, graph, server_uri=''):
    if server_uri == '':
        # Retain the original call, including its native default of None.
        return adapter.add_fleet(fleet_name, traits, graph)
    return adapter.add_fleet(fleet_name, traits, graph, server_uri)
