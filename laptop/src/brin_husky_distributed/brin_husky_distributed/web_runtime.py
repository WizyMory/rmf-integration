"""Humble Web compatibility and endpoint validation, without opening sockets."""
import ipaddress
from pathlib import Path
import subprocess
from urllib.parse import urlsplit


WEB_REVISION = 'e2861c292bb27014435452e74faa825ecb0e8d91'


def validate_server_uri(uri, remote=False):
    if not uri:
        return ''
    try:
        parsed = urlsplit(uri)
        port = parsed.port
    except ValueError as error:
        raise ValueError('Invalid RMF Web server_uri') from error
    if (parsed.scheme not in ('ws', 'wss') or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.fragment or port == 0):
        raise ValueError('server_uri must be a ws:// or wss:// endpoint without credentials')
    if remote:
        host = parsed.hostname.lower().rstrip('.')
        local = host == 'localhost' or host.endswith('.localhost')
        try:
            address = ipaddress.ip_address(host)
            local = local or address.is_loopback or address.is_unspecified
            if address.version == 6 and address.ipv4_mapped:
                local = local or address.ipv4_mapped.is_loopback
        except ValueError:
            pass  # A LAN hostname can be resolved by the robot at runtime.
        if local:
            raise ValueError('Husky server_uri must use the laptop LAN address, not localhost')
    return uri


def web_paths(root):
    root = Path(root).expanduser().resolve()
    revision = subprocess.run(
        ['git', '-C', str(root), 'rev-parse', 'HEAD'],
        check=True, capture_output=True, text=True).stdout.strip()
    if revision != WEB_REVISION:
        raise ValueError(f'RMF Web requires the reviewed Humble revision {WEB_REVISION}; '
                         f'found {revision}')
    python = root / '.venv/bin/python'
    api = root / 'packages/api-server'
    if not python.is_file() or not (api / 'api_server/__main__.py').is_file():
        raise FileNotFoundError('RMF Web checkout or .venv is incomplete; see WEB.md')
    return python, api
