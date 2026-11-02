"""Canonical gedungWS_0 assets match the existing laptop announcement."""
import hashlib
import json
from pathlib import Path

import yaml


def resolve_profile(share=None):
    if share is None:
        from ament_index_python.packages import get_package_share_directory
        share = get_package_share_directory('brin_devi_fleet_adapter')
    share = Path(share)
    files = [share / 'maps/gedungWS_0_rmf.building.yaml',
             share / 'nav_graphs/gedungWS_0.yaml',
             share / 'maps/gedungWS_0_rmf.yaml',
             share / 'maps/gedungWS_0.pgm',
             share / 'maps/gedungWS_0_fleet.yaml']
    digest = hashlib.sha256(b'gedungWS_0')
    for path in files:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return {'name': 'gedungWS_0', 'digest': digest.hexdigest(),
            'graph': str(files[1]), 'map_yaml': str(files[2])}


def load_settings(path):
    settings = yaml.safe_load(Path(path).read_text())
    if (settings['robot_name'], settings['fleet_name'], settings['robot_domain_id'],
            settings['rmf_domain_id'], settings['traffic_profile']) != (
            'devi', 'Devi', 73, 0, 'gedungWS_0'):
        raise ValueError('Expected physical Devi domain 73 and RMF domain 0 / gedungWS_0')
    return settings


def main():
    print(json.dumps(resolve_profile(), indent=2))
