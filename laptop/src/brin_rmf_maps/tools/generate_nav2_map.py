#!/usr/bin/env python3
"""Generate map_server metadata without resampling or modifying the image."""
import argparse
import os
from pathlib import Path
import yaml
from map_geometry import load_geometry


def generate(building, output):
    _, _, image, (width, height), scale, ratios = load_geometry(building)
    output = Path(output)
    result = dict(image=os.path.relpath(image, output.parent), resolution=scale,
                  origin=[0.0, -height * scale, 0.0], negate=0,
                  occupied_thresh=0.65, free_thresh=0.196, mode='trinary')
    output.write_text(yaml.safe_dump(result, sort_keys=False))
    print(f'{width} x {height}; measurement scales={ratios}; mean={scale:.12f}')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('building')
    parser.add_argument('output')
    args = parser.parse_args()
    generate(args.building, args.output)
