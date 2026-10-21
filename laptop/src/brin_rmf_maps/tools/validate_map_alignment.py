#!/usr/bin/env python3
"""Fail if the image, map-server origin and generated graph disagree."""
import argparse
import math
from pathlib import Path
import yaml
from map_geometry import image_to_map, load_geometry

REQUIRED = ('husky_0', 'husky_1', 'pantry', 'lab_bengkel', 'lab_bengkel2', 'lab_dinamika')


def validate(building, graph, occupancy, tolerance=0.10, allow_derived=False,
             derived_image_name='brin_0_nav2.png'):
    _, floor, image, (_, height), scale, _ = load_geometry(building)
    nav = yaml.safe_load(Path(graph).read_text())['levels']['L1']
    metadata = yaml.safe_load(Path(occupancy).read_text())
    actual_image = (Path(occupancy).parent / metadata['image']).resolve()
    if actual_image != image.resolve():
        if not allow_derived or actual_image.name != derived_image_name:
            raise ValueError('Occupancy must reference the original or explicitly validated derived image')
        from PIL import Image
        with Image.open(actual_image) as actual, Image.open(image) as original:
            if actual.size != original.size:
                raise ValueError('Derived image dimensions changed')
    assert abs(metadata['resolution'] - scale) < 1e-12, 'resolution mismatch'
    assert abs(metadata['origin'][2]) < 1e-12, 'unexpected rotation'
    by_name = {v[2]['name']: v[:2] for v in nav['vertices'] if v[2].get('name')}
    source = {v[3]: v[:2] for v in floor['vertices'] if v[3]}
    errors = {}
    for name in REQUIRED:
        x, y = source[name]
        expected = image_to_map(x, y, scale)
        # Continuous image boundaries; map-server cell centers add +/- half a
        # pixel. Graph coordinates are continuous, not snapped to cell centers.
        map_xy = [metadata['origin'][0] + x * metadata['resolution'],
                  metadata['origin'][1] + (height-y) * metadata['resolution']]
        error = max(math.dist(expected, by_name[name]), math.dist(map_xy, by_name[name]))
        errors[name] = error
        print(f'{name:16} RMF={by_name[name]} expected={expected} error={error:.9f} m')
        if error > tolerance:
            raise ValueError(f'{name}: {error:.6f} m exceeds {tolerance} m')
    return errors


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('building'); p.add_argument('graph'); p.add_argument('occupancy')
    p.add_argument('--tolerance', type=float, default=0.10)
    p.add_argument('--allow-derived', action='store_true')
    a = p.parse_args()
    validate(a.building, a.graph, a.occupancy, a.tolerance, a.allow_derived)
