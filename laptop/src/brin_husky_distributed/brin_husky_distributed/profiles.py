"""Resolve one authoritative BRIN map/graph bundle and its cross-host digest."""
import hashlib
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
import yaml


def resolve_profile(name, maps_share=None):
    share = Path(maps_share or get_package_share_directory('brin_rmf_maps'))
    profiles = yaml.safe_load((share / 'maps/traffic_profiles.yaml').read_text())
    if name not in profiles['profiles']:
        raise ValueError(f'Unknown traffic_profile {name!r}; choose '
                         f'{sorted(profiles["profiles"])}')
    entry = profiles['profiles'][name]
    building = share / 'maps' / entry['building_map']
    graph = share / 'nav_graphs' / entry['nav_graph']
    map_yaml = share / 'maps' / entry['nav2_map']
    for path in (building, graph, map_yaml):
        if not path.is_file():
            raise FileNotFoundError(path)
    metadata = yaml.safe_load(map_yaml.read_text())
    image = map_yaml.parent / metadata['image']
    if not image.is_file():
        raise FileNotFoundError(image)
    fleet_config = share / 'maps' / entry['fleet_config'] if 'fleet_config' in entry else None
    if fleet_config is not None and not fleet_config.is_file():
        raise FileNotFoundError(fleet_config)
    digest = hashlib.sha256()
    digest.update(name.encode('utf-8'))
    for path in (building, graph, map_yaml, image) + ((fleet_config,) if fleet_config else ()):
        digest.update(path.name.encode('utf-8'))
        digest.update(path.read_bytes())
    result = {'name': name, 'building': building, 'graph': graph,
              'map_yaml': map_yaml, 'image': image, 'digest': digest.hexdigest()}
    if fleet_config is not None:
        result['fleet_config'] = fleet_config
    return result
