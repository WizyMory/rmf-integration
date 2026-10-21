#!/usr/bin/env python3
"""Independently validate the policy-derived Nav2 map and correction mask."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image
import yaml

from generate_nav2_occupancy import (
    REQUIRED, classify, derive, load_policy, oriented_sweep, select_known_areas)
from map_geometry import load_geometry
from validate_map_alignment import validate


def audit(package, nav2_config, metadata=None, policy_path=None,
          building_name='brin_0.building.yaml', graph_name=None,
          output_prefix='brin_0'):
    package = Path(package).resolve()
    if Path(building_name).name != building_name or Path(output_prefix).name != output_prefix:
        raise ValueError('Building name and output prefix must be plain filenames')
    building = package/'maps'/building_name
    _, floor, original, size, scale, _ = load_geometry(building)
    metadata = (Path(metadata) if metadata else
                package/'maps'/f'{output_prefix}_nav2.candidate.yaml')
    policy_path = Path(policy_path) if policy_path else package/'maps/nav2_occupancy_policy.yaml'
    policy = load_policy(policy_path)
    config = yaml.safe_load(Path(nav2_config).read_text())['local_costmap']['local_costmap']['ros__parameters']
    footprint = yaml.safe_load(config['footprint'])
    padding = float(config['footprint_padding'])
    margin = float(policy['clearance']['additional_margin_m'])
    half_length = max(abs(point[0]) for point in footprint)+padding+margin
    half_width = max(abs(point[1]) for point in footprint)+padding+margin

    params = yaml.safe_load(metadata.read_text())
    for key, expected in [('negate', 0), ('mode', 'trinary'),
                          ('occupied_thresh', 0.65), ('free_thresh', 0.196)]:
        if params[key] != expected:
            raise ValueError(f'Unexpected {key}: {params[key]}')
    source = np.asarray(Image.open(original).convert('L'))
    image = Image.open(metadata.parent/params['image'])
    if image.size != size or image.mode != 'L':
        raise ValueError('Candidate dimensions or grayscale format changed')
    candidate = np.asarray(image)
    expected, expected_corrections, _, walls, diagnostics = derive(
        source, floor, scale, half_length, half_width,
        float(policy['clearance']['wall_thickness_m']), int(policy['fleet_graph_index']),
        select_known_areas(policy, building.name))
    unexpected_pixels = int(np.count_nonzero(candidate != expected))
    if unexpected_pixels:
        raise ValueError(f'Candidate differs from policy-derived output at {unexpected_pixels} pixels')
    correction_path = package/'maps'/f'{output_prefix}_nav2_corrections.png'
    correction_image = Image.open(correction_path)
    if correction_image.size != size or correction_image.mode != 'L':
        raise ValueError('Correction-mask dimensions or grayscale format changed')
    corrections = np.asarray(correction_image)
    correction_mismatches = int(np.count_nonzero(corrections != expected_corrections))
    if correction_mismatches:
        raise ValueError(f'Correction mask differs from policy at {correction_mismatches} pixels')

    alignment = validate(
        building, package/'nav_graphs'/(graph_name or f'{policy["fleet_graph_index"]}.yaml'),
        metadata, allow_derived=True,
        derived_image_name=f'{output_prefix}_nav2.png')
    occupied, free, _ = classify(candidate)
    bad_lanes = []
    for lane in diagnostics['lanes']:
        region, mask, outside = oriented_sweep(
            candidate.shape, lane['image_start'], lane['image_end'],
            half_length/scale, half_width/scale)
        cells = int(np.count_nonzero(mask & ~free[region]))
        if cells or outside:
            bad_lanes.append({'building_lane_index': lane['building_lane_index'],
                              'building_vertices': lane['building_vertices'],
                              'nonfree_cells': cells, 'out_of_bounds': outside})
    wall_cells_not_occupied = int(np.count_nonzero(walls & ~occupied))
    waypoints = {
        name: {'accepted': check['accepted'],
               'incident_lane_indexes': check['incident_lane_indexes']}
        for name, check in diagnostics['required_waypoints'].items()
    }
    changed = candidate != source
    changed_occupied = int(np.count_nonzero(changed & classify(source)[0]))
    result = {
        'accepted': (diagnostics['accepted'] and not bad_lanes
                     and set(waypoints) == set(REQUIRED)
                     and wall_cells_not_occupied == 0),
        'policy': str(policy_path),
        'changed_cells': int(np.count_nonzero(changed)),
        'changed_reference_occupied_cells': changed_occupied,
        'correction_mask_mismatches': correction_mismatches,
        'unexpected_candidate_pixels': unexpected_pixels,
        'traffic_editor_wall_cells_not_occupied': wall_cells_not_occupied,
        'known_areas': diagnostics['known_areas'],
        'alignment_errors_m': alignment,
        'blocked_lanes': bad_lanes,
        'waypoints': waypoints,
        'reachability': diagnostics['reachability'],
    }
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--nav2-config', type=Path, required=True)
    parser.add_argument('--metadata', type=Path)
    parser.add_argument('--policy', type=Path)
    parser.add_argument('--building', default='brin_0.building.yaml')
    parser.add_argument('--graph')
    parser.add_argument('--output-prefix', default='brin_0')
    args = parser.parse_args()
    result = audit(args.package, args.nav2_config, args.metadata, args.policy,
                   args.building, args.graph, args.output_prefix)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result['accepted'] else 1)
