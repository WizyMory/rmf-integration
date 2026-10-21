#!/usr/bin/env python3
"""Derive a Nav2 map from explicit Traffic Editor occupancy policy.

The reference PNG is visual evidence, not the collision authority. Traffic
Editor walls are rasterized as occupied, open doors are omitted, and the
selected fleet graph is cleared with an oriented Husky footprint sweep.
Explicit profile-specific Traffic Editor floor polygons may additionally be
approved as known space. Every changed pixel is recorded in a correction mask
and provenance report.
"""
import argparse
from collections import defaultdict, deque
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw
import yaml

from map_geometry import load_geometry, image_to_map
from validate_map_alignment import validate

REQUIRED = ('husky_0', 'husky_1', 'pantry', 'lab_bengkel', 'lab_bengkel2', 'lab_dinamika')
CORRECTION_CODES = {
    'unchanged': 0,
    'approved_area_unknown_to_free': 64,
    'reference_unknown_to_free': 85,
    'approved_area_occupied_to_free': 128,
    'reference_occupied_to_free': 170,
    'traffic_editor_wall_enforced': 255,
}


def classify(image, occupied_thresh=0.65, free_thresh=0.196):
    probability = 1.0-image.astype(float)/255.0
    occupied = probability > occupied_thresh
    free = probability < free_thresh
    return occupied, free, ~(occupied | free)


def capsule(shape, start, end, radius):
    """Return a conservative raster mask around a line segment."""
    radius += math.sqrt(0.5)
    height, width = shape
    x, y = start
    u, v = end
    left = max(0, math.floor(min(x, u)-radius))
    right = min(width, math.ceil(max(x, u)+radius+1))
    top = max(0, math.floor(min(y, v)-radius))
    bottom = min(height, math.ceil(max(y, v)+radius+1))
    yy, xx = np.mgrid[top:bottom, left:right]
    dx, dy = u-x, v-y
    length2 = dx*dx+dy*dy
    fraction = np.clip(((xx-x)*dx+(yy-y)*dy)/length2, 0, 1) if length2 else np.zeros_like(xx)
    distance = np.hypot(xx-x-fraction*dx, yy-y-fraction*dy)
    outside = (min(x, u)-radius < 0 or min(y, v)-radius < 0
               or max(x, u)+radius >= width or max(y, v)+radius >= height)
    return (slice(top, bottom), slice(left, right)), distance <= radius, distance, outside


def oriented_sweep(shape, start, end, half_length_px, half_width_px):
    """Rasterize a rectangle swept along a lane at its driving orientation."""
    height, width = shape
    x, y = start
    u, v = end
    dx, dy = u-x, v-y
    length = math.hypot(dx, dy)
    if not length:
        raise ValueError(f'Zero-length lane at {start}')
    tx, ty = dx/length, dy/length
    nx, ny = -ty, tx
    quantization = math.sqrt(0.5)
    along = half_length_px+quantization
    across = half_width_px+quantization
    corners = [
        (x-tx*along+nx*across, y-ty*along+ny*across),
        (x-tx*along-nx*across, y-ty*along-ny*across),
        (u+tx*along+nx*across, v+ty*along+ny*across),
        (u+tx*along-nx*across, v+ty*along-ny*across),
    ]
    outside = any(px < 0 or py < 0 or px >= width or py >= height for px, py in corners)
    left = max(0, math.floor(min(px for px, _ in corners)))
    right = min(width, math.ceil(max(px for px, _ in corners)+1))
    top = max(0, math.floor(min(py for _, py in corners)))
    bottom = min(height, math.ceil(max(py for _, py in corners)+1))
    yy, xx = np.mgrid[top:bottom, left:right]
    relx, rely = xx-x, yy-y
    longitudinal = relx*tx+rely*ty
    lateral = relx*nx+rely*ny
    mask = ((longitudinal >= -along) & (longitudinal <= length+along)
            & (np.abs(lateral) <= across))
    return (slice(top, bottom), slice(left, right)), mask, outside


def structural_wall_mask(shape, floor, scale, wall_thickness_m):
    """Rasterize only Traffic Editor walls; doors remain open by policy."""
    result = np.zeros(shape, dtype=bool)
    radius_px = wall_thickness_m/(2.0*scale)
    for a, b, _ in floor.get('walls', []):
        region, mask, _, _ = capsule(shape, floor['vertices'][a][:2],
                                     floor['vertices'][b][:2], radius_px)
        result[region] |= mask
    return result


def select_known_areas(policy, building_name):
    """Return explicit known-area overrides for one building profile."""
    areas = policy.get('known_areas', [])
    if not isinstance(areas, list):
        raise ValueError('known_areas must be a list')
    selected = []
    names = set()
    for area in areas:
        if not isinstance(area, dict):
            raise ValueError('Each known area must be a mapping')
        required = {'name', 'building', 'floor_polygon_index', 'required_waypoints'}
        if set(area) != required:
            raise ValueError(f'Known area must contain exactly {sorted(required)}')
        if area['name'] in names:
            raise ValueError(f'Duplicate known area name: {area["name"]}')
        names.add(area['name'])
        if area['building'] == building_name:
            selected.append(area)
    return selected


def known_area_mask(shape, floor, areas):
    """Rasterize user-approved Traffic Editor floor polygons as known space."""
    result = np.zeros(shape, dtype=bool)
    details = []
    names = {vertex[3]: vertex for vertex in floor['vertices'] if vertex[3]}
    polygons = floor.get('floors', [])
    height, width = shape
    for area in areas:
        index = area['floor_polygon_index']
        if not isinstance(index, int) or index < 0 or index >= len(polygons):
            raise ValueError(f'Known area {area["name"]} has invalid floor polygon index {index}')
        vertex_indexes = polygons[index]['vertices']
        points = [floor['vertices'][vertex_index][:2] for vertex_index in vertex_indexes]
        if any(x < 0 or y < 0 or x >= width or y >= height for x, y in points):
            raise ValueError(f'Known area {area["name"]} extends outside the reference image')
        canvas = Image.new('1', (width, height), 0)
        ImageDraw.Draw(canvas).polygon([tuple(point) for point in points], fill=1)
        mask = np.asarray(canvas, dtype=bool)
        missing = [name for name in area['required_waypoints'] if name not in names]
        if missing:
            raise ValueError(f'Known area {area["name"]} is missing waypoints {missing}')
        outside = []
        for name in area['required_waypoints']:
            x, y = names[name][:2]
            px = min(width-1, max(0, int(round(x))))
            py = min(height-1, max(0, int(round(y))))
            if not mask[py, px]:
                outside.append(name)
        if outside:
            raise ValueError(
                f'Known area {area["name"]} does not contain waypoints {outside}')
        result |= mask
        details.append({
            'name': area['name'],
            'floor_polygon_index': index,
            'required_waypoints': area['required_waypoints'],
            'polygon_vertex_indexes': vertex_indexes,
            'raster_cells': int(np.count_nonzero(mask)),
        })
    return result, details


def graph_reachability(floor, graph_index, accepted_lane_indexes):
    names = {vertex[3]: index for index, vertex in enumerate(floor['vertices']) if vertex[3]}
    adjacency = defaultdict(set)
    for lane_index, (a, b, params) in enumerate(floor['lanes']):
        if params['graph_idx'][1] != graph_index or lane_index not in accepted_lane_indexes:
            continue
        adjacency[a].add(b)
        if params.get('bidirectional', [None, False])[1]:
            adjacency[b].add(a)
    reachable = {}
    spawn_names = [v[3] for v in floor['vertices']
                   if len(v) > 4 and 'spawn_robot_name' in v[4]]
    for start_name in spawn_names or ('husky_0', 'husky_1'):
        if start_name not in names:
            reachable[start_name] = []
            continue
        visited = {names[start_name]}
        queue = deque(visited)
        while queue:
            for target in adjacency[queue.popleft()]:
                if target not in visited:
                    visited.add(target)
                    queue.append(target)
        reachable[start_name] = [name for name in REQUIRED if name in names and names[name] in visited]
    accepted = all(set(values) == set(REQUIRED) for values in reachable.values())
    return {'reachable_required_waypoints': reachable, 'accepted': accepted}


def load_policy(path):
    policy = yaml.safe_load(Path(path).read_text())
    if policy.get('version') != 1:
        raise ValueError('Unsupported occupancy policy version')
    if policy['authority'] != {
            'reference_image': 'visual_reference',
            'traffic_editor_walls': 'structural_obstacles',
            'traffic_editor_doors': 'traversable_when_open'}:
        raise ValueError('Occupancy authority policy must be explicit and complete')
    return policy


def derive(source, floor, scale, half_length_m, half_width_m, wall_thickness_m,
           graph_index=1, known_areas=()):
    occupied, _, unknown = classify(source)
    corridor = np.zeros(source.shape, dtype=bool)
    walls = structural_wall_mask(source.shape, floor, scale, wall_thickness_m)
    approved_areas, approved_area_details = known_area_mask(
        source.shape, floor, known_areas)
    lanes = []
    accepted_lane_indexes = set()
    half_length_px = half_length_m/scale
    half_width_px = half_width_m/scale
    for index, (a, b, params) in enumerate(floor['lanes']):
        if params['graph_idx'][1] != graph_index:
            continue
        start, end = floor['vertices'][a][:2], floor['vertices'][b][:2]
        region, mask, outside = oriented_sweep(
            source.shape, start, end, half_length_px, half_width_px)
        corridor[region] |= mask
        structural_overlap = walls[region] & mask
        reference_occupied = occupied[region] & mask & ~walls[region]
        accepted = not outside and not np.any(structural_overlap)
        if accepted:
            accepted_lane_indexes.add(index)
        rows, cols = np.nonzero(reference_occupied)
        first = None
        if len(rows):
            pixel = [int(cols[0]+region[1].start), int(rows[0]+region[0].start)]
            first = {'pixel_xy': pixel, 'metric_xy': image_to_map(*pixel, scale),
                     'intensity': int(source[pixel[1], pixel[0]])}
        lanes.append({
            'building_lane_index': index,
            'building_vertices': [a, b],
            'endpoint_names': [floor['vertices'][a][3], floor['vertices'][b][3]],
            'image_start': start,
            'image_end': end,
            'reference_unknown_cells_cleared': int(np.count_nonzero(unknown[region] & mask & ~walls[region])),
            'reference_occupied_cells_cleared': int(len(rows)),
            'structural_wall_cells': int(np.count_nonzero(structural_overlap)),
            'out_of_bounds': bool(outside),
            'first_reference_occupied': first,
            'accepted': accepted,
        })
    if not lanes:
        raise ValueError(f'No lanes for graph index {graph_index}')

    required = {}
    for name in REQUIRED:
        matches = [i for i, vertex in enumerate(floor['vertices']) if vertex[3] == name]
        if not matches:
            continue
        vertex_index = matches[0]
        incident = [lane['building_lane_index'] for lane in lanes
                    if vertex_index in lane['building_vertices']]
        accepted = bool(incident) and all(i in accepted_lane_indexes for i in incident)
        point = floor['vertices'][vertex_index][:2]
        required[name] = {'building_vertex_index': vertex_index, 'pixel_xy': point,
                          'metric_xy': image_to_map(*point, scale),
                          'incident_lane_indexes': incident, 'accepted': accepted}
    missing = sorted(set(REQUIRED)-required.keys())
    reachability = graph_reachability(floor, graph_index, accepted_lane_indexes)

    route_clearable = corridor & ~walls
    area_clearable = approved_areas & ~corridor & ~walls
    route_unknown = route_clearable & unknown
    route_occupied = route_clearable & occupied
    area_unknown = area_clearable & unknown
    area_occupied = area_clearable & occupied
    enforce_walls = walls & (source != 0)
    derived = source.copy()
    derived[route_unknown | route_occupied | area_unknown | area_occupied] = 254
    derived[walls] = 0
    corrections = np.zeros(source.shape, dtype=np.uint8)
    corrections[area_unknown] = CORRECTION_CODES['approved_area_unknown_to_free']
    corrections[area_occupied] = CORRECTION_CODES['approved_area_occupied_to_free']
    corrections[route_unknown] = CORRECTION_CODES['reference_unknown_to_free']
    corrections[route_occupied] = CORRECTION_CODES['reference_occupied_to_free']
    corrections[enforce_walls] = CORRECTION_CODES['traffic_editor_wall_enforced']
    changed = derived != source
    if np.any(changed & (corrections == CORRECTION_CODES['unchanged'])):
        raise AssertionError('Every changed pixel must have a correction code')

    report = {
        'graph_index': graph_index,
        'sweep': {'half_length_m': half_length_m, 'half_width_m': half_width_m,
                  'full_length_m': 2*half_length_m, 'full_width_m': 2*half_width_m},
        'wall_thickness_m': wall_thickness_m,
        'doors': 'open; door segments are not structural walls',
        'correction_codes': CORRECTION_CODES,
        'changed_cells': int(np.count_nonzero(changed)),
        'changed_reference_unknown_to_free': int(np.count_nonzero(route_unknown | area_unknown)),
        'changed_reference_occupied_to_free': int(np.count_nonzero(route_occupied | area_occupied)),
        'changed_route_unknown_to_free': int(np.count_nonzero(route_unknown)),
        'changed_route_occupied_to_free': int(np.count_nonzero(route_occupied)),
        'changed_approved_area_unknown_to_free': int(np.count_nonzero(area_unknown)),
        'changed_approved_area_occupied_to_free': int(np.count_nonzero(area_occupied)),
        'changed_traffic_editor_wall_enforced': int(np.count_nonzero(enforce_walls)),
        'known_areas': approved_area_details,
        'lanes': lanes,
        'required_waypoints': required,
        'missing_waypoints': missing,
        'reachability': reachability,
    }
    report['accepted'] = (not missing and all(lane['accepted'] for lane in lanes)
                          and all(value['accepted'] for value in required.values())
                          and reachability['accepted'])
    return derived, corrections, corridor, walls, report


def run(package, nav2_config, policy_path=None, building_name='brin_0.building.yaml',
        graph_name=None, output_prefix='brin_0'):
    package = Path(package).resolve()
    if Path(building_name).name != building_name or Path(output_prefix).name != output_prefix:
        raise ValueError('Building name and output prefix must be plain filenames')
    building = package/'maps'/building_name
    policy_path = Path(policy_path) if policy_path else package/'maps/nav2_occupancy_policy.yaml'
    policy = load_policy(policy_path)
    _, floor, image_path, dimensions, scale, _ = load_geometry(building)
    config = yaml.safe_load(Path(nav2_config).read_text())['local_costmap']['local_costmap']['ros__parameters']
    footprint = yaml.safe_load(config['footprint'])
    padding = float(config['footprint_padding'])
    margin = float(policy['clearance']['additional_margin_m'])
    half_length = max(abs(point[0]) for point in footprint)+padding+margin
    half_width = max(abs(point[1]) for point in footprint)+padding+margin
    source = np.asarray(Image.open(image_path).convert('L'))
    derived, corrections, _, _, report = derive(
        source, floor, scale, half_length, half_width,
        float(policy['clearance']['wall_thickness_m']),
        int(policy['fleet_graph_index']), select_known_areas(policy, building.name))
    report.update(
        policy_file=policy_path.name,
        policy_sha256=hashlib.sha256(policy_path.read_bytes()).hexdigest(),
        authority=policy['authority'],
        source_sha256=hashlib.sha256(image_path.read_bytes()).hexdigest(),
        building_sha256=hashlib.sha256(building.read_bytes()).hexdigest(),
        dimensions=list(dimensions), resolution=scale, footprint=footprint,
        footprint_padding_m=padding, additional_margin_m=margin,
        source_image=image_path.name, derived_image=f'{output_prefix}_nav2.png',
        correction_mask=f'{output_prefix}_nav2_corrections.png', promoted=False)
    output = package/'maps'/report['derived_image']
    correction_output = package/'maps'/report['correction_mask']
    Image.fromarray(derived).save(output)
    Image.fromarray(corrections).save(correction_output)
    report['derived_sha256'] = hashlib.sha256(output.read_bytes()).hexdigest()
    report['correction_mask_sha256'] = hashlib.sha256(correction_output.read_bytes()).hexdigest()
    candidate = package/'maps'/f'{output_prefix}_nav2.candidate.yaml'
    metadata = dict(image=output.name, resolution=scale,
                    origin=[0.0, -dimensions[1]*scale, 0.0], negate=0,
                    occupied_thresh=0.65, free_thresh=0.196, mode='trinary')
    candidate.write_text(yaml.safe_dump(metadata, sort_keys=False))
    report['alignment_errors_m'] = validate(
        building, package/'nav_graphs'/(graph_name or f'{policy["fleet_graph_index"]}.yaml'),
        candidate, allow_derived=True,
        derived_image_name=f'{output_prefix}_nav2.png')
    promoted = package/'maps'/f'{output_prefix}.yaml'
    if report['accepted']:
        promoted.write_text(candidate.read_text())
        report['promoted'] = True
    report_name = ('occupancy_report.json' if output_prefix == 'brin_0'
                   else f'{output_prefix}_occupancy_report.json')
    (package/'maps'/report_name).write_text(json.dumps(report, indent=2)+'\n')
    failed = [lane for lane in report['lanes'] if not lane['accepted']]
    print(f'Oriented sweep {2*half_length:.3f} x {2*half_width:.3f} m; '
          f'cleared {report["changed_route_unknown_to_free"]} route unknown and '
          f'{report["changed_route_occupied_to_free"]} route occupied cells')
    print(f'Approved known areas cleared '
          f'{report["changed_approved_area_unknown_to_free"]} unknown and '
          f'{report["changed_approved_area_occupied_to_free"]} occupied cells')
    print(f'Enforced {report["changed_traffic_editor_wall_enforced"]} Traffic Editor wall cells')
    for lane in failed:
        print(f'BLOCKED lane {lane["building_lane_index"]} vertices {lane["building_vertices"]}: '
              f'{lane["structural_wall_cells"]} structural wall cells, '
              f'out_of_bounds={lane["out_of_bounds"]}')
    print(f'Promoted {promoted.name}' if report['promoted'] else
          f'NOT PROMOTED: {len(failed)} structural conflicts; inspect maps/occupancy_report.json')
    return report['accepted']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--nav2-config', type=Path, required=True)
    parser.add_argument('--policy', type=Path)
    parser.add_argument('--building', default='brin_0.building.yaml')
    parser.add_argument('--graph')
    parser.add_argument('--output-prefix', default='brin_0')
    args = parser.parse_args()
    sys.exit(0 if run(args.package, args.nav2_config, args.policy, args.building,
                      args.graph, args.output_prefix) else 1)
