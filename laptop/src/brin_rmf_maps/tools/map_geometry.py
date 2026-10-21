"""The one explicit transform from BRIN image coordinates to RMF/Nav2 map."""
import math
import re
from pathlib import Path
import yaml
from PIL import Image


def load_geometry(building, level='L1'):
    building = Path(building)
    data = yaml.safe_load(building.read_text())
    if data.get('coordinate_system') != 'reference_image':
        raise ValueError('This pipeline requires reference_image coordinates')
    if len(data['levels']) != 1:
        raise ValueError('Multi-level registration requires an explicit transform')
    floor = data['levels'][level]
    ratios = []
    for start, end, parameters in floor['measurements']:
        a, b = floor['vertices'][start], floor['vertices'][end]
        pixels = math.hypot(a[0] - b[0], a[1] - b[1])
        if pixels <= 0:
            raise ValueError('Zero-length map measurement')
        ratios.append(float(parameters['distance'][1]) / pixels)
    if not ratios or min(ratios) <= 0:
        raise ValueError('Positive scale measurements are required')
    # Matches installed Level.calculate_scale_using_measurements: arithmetic
    # mean of individual distance/pixel-length ratios, not a weighted fit.
    scale = sum(ratios) / len(ratios)
    image = building.parent / floor['drawing']['filename']
    with Image.open(image) as im:
        dimensions = im.size
    return data, floor, image, dimensions, scale, ratios


def image_to_map(x, y, scale):
    return [x * scale, -y * scale]


def graph_spawns(graph, level='L1'):
    floor = yaml.safe_load(Path(graph).read_text())['levels'][level]
    vertices = floor['vertices']
    result = {}
    for i, vertex in enumerate(vertices):
        name = vertex[2].get('spawn_robot_name')
        if not name:
            continue
        if not re.fullmatch(r'husky_[0-9]+', name) or name in result:
            raise ValueError(f'Invalid or duplicate spawn robot: {name}')
        if vertex[2].get('spawn_robot_type') != 'HuskyA200':
            raise ValueError(f'Unsupported robot type for {name}')
        charger = vertex[2].get('name')
        if not charger or not vertex[2].get('is_charger'):
            raise ValueError(f'{name} spawn must have a named charger waypoint')
        neighbors = [b for a, b, *_ in floor['lanes'] if a == i and b != i]
        if not neighbors:
            raise ValueError(f'{name} has no outgoing lane')
        target = vertices[neighbors[0]]
        result[name] = dict(x=vertex[0], y=vertex[1],
                            yaw=math.atan2(target[1]-vertex[1], target[0]-vertex[0]),
                            waypoint=i, level=level, charger=charger)
    if not result:
        raise ValueError('No Husky spawn metadata in graph')
    return dict(sorted(result.items()))
