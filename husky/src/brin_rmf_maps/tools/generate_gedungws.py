"""Generate a metric RMF bundle without changing the user's SLAM/editor inputs."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile

import numpy as np
from PIL import Image
import yaml
from generate_nav2_occupancy import oriented_sweep, classify


def generate(package, nav2_config):
    package = Path(package).resolve()
    maps = package/'maps'
    source = maps/'gedungWS_0.building.yaml'
    original = yaml.safe_load(source.read_text())
    metadata = yaml.safe_load((maps/'gedungWS_0.yaml').read_text())
    resolution = float(metadata['resolution'])
    assert resolution > 0 and original['coordinate_system'] == 'reference_image'
    assert len(original['levels']) == 1
    level_name, level = next(iter(original['levels'].items()))
    drawing = Image.open(maps/level['drawing']['filename']).convert('L')
    occupancy = Image.open(maps/metadata['image']).convert('L')
    assert np.array_equal(drawing, occupancy), 'Drawing and SLAM image differ'
    derived = copy.deepcopy(original)
    floor = derived['levels'].pop(level_name)
    derived['levels']['L1'] = floor
    # Infer a measurement from existing vertices and the supplied SLAM scale.
    a, b = floor['vertices'][:2]
    distance = math.dist(a[:2], b[:2])*resolution
    assert distance > 0
    floor['measurements'] = [[0, 1, {'distance': [3, distance]}]]
    building = maps/'gedungWS_0_rmf.building.yaml'
    building.write_text(yaml.safe_dump(derived, sort_keys=False))
    with tempfile.TemporaryDirectory(prefix='gedungws_graph_') as temporary:
        subprocess.run(['ros2', 'run', 'rmf_building_map_tools', 'building_map_generator',
                        'nav', str(building), temporary], check=True)
        indexes = {lane[2]['graph_idx'][1] for lane in floor['lanes']}
        assert len(indexes) == 1
        graph = yaml.safe_load((Path(temporary)/f'{indexes.pop()}.yaml').read_text())
    for lane in graph['levels']['L1']['lanes']:
        lane[2].pop('door_name', None)
    (package/'nav_graphs/gedungWS_0.yaml').write_text(yaml.safe_dump(graph))
    active = copy.deepcopy(metadata)
    active['origin'] = [0.0, -occupancy.height*resolution, 0.0]
    (maps/'gedungWS_0_rmf.yaml').write_text(yaml.safe_dump(active, sort_keys=False))
    fleet = yaml.safe_load((package.parent/'brin_husky_distributed/config/fleet_config.yaml').read_text())
    fleet['robots']['husky_0']['charger'] = 'ws_p0'
    (maps/'gedungWS_0_fleet.yaml').write_text(yaml.safe_dump(fleet, sort_keys=False))
    config = yaml.safe_load(Path(nav2_config).read_text())
    footprint_config = config['local_costmap']['local_costmap']['ros__parameters']
    footprint = yaml.safe_load(footprint_config['footprint'])
    padding = float(footprint_config['footprint_padding'])
    half_length = max(abs(point[0]) for point in footprint)+padding
    half_width = max(abs(point[1]) for point in footprint)+padding
    nav = graph['levels']['L1']
    named = {v[2].get('name'): v for v in nav['vertices'] if v[2].get('name')}
    assert 'ws_p0' in named and named['ws_p0'][2].get('is_charger')
    for vertex in floor['vertices']:
        if vertex[3] in named:
            assert math.dist(named[vertex[3]][:2], [vertex[0]*resolution, -vertex[1]*resolution]) < 1e-8
    free = classify(np.asarray(occupancy), metadata['occupied_thresh'], metadata['free_thresh'])[1]
    blocked = []
    for index, (start, end, _) in enumerate(floor['lanes']):
        region, mask, outside = oriented_sweep(
            free.shape, floor['vertices'][start][:2], floor['vertices'][end][:2],
            half_length/resolution, half_width/resolution)
        cells = int(np.count_nonzero(mask & ~free[region]))
        if cells or outside:
            blocked.append({'lane': index, 'vertices': [start, end], 'nonfree_cells': cells,
                            'outside': outside})
    report = {'source_level': level_name, 'runtime_level': 'L1', 'resolution': resolution,
              'original_origin': metadata['origin'], 'runtime_origin': active['origin'],
              'footprint_sweep_m': [2*half_length, 2*half_width],
              'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'vertices': len(nav['vertices']), 'directed_lanes': len(nav['lanes']),
              'named_waypoints': sorted(named), 'blocked_footprint_sweeps': blocked,
              'occupancy_pixels_changed': 0, 'motion_tested': False}
    (maps/'gedungWS_0_report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--nav2-config', type=Path, required=True)
    options = parser.parse_args()
    generate(options.package, options.nav2_config)
