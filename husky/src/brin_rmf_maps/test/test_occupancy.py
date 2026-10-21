from pathlib import Path
import sys

import numpy as np
from PIL import Image
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from generate_nav2_occupancy import CORRECTION_CODES, REQUIRED, derive, run
from generate_nav2_map import generate
from validate_nav2_occupancy import audit


def floor(structural_wall=False, door=False):
    vertices = [[15+i*10, 30, 0, name, {}] for i, name in enumerate(REQUIRED)]
    vertices += [[40, 20, 0, '', {}], [40, 40, 0, '', {}]]
    result = {
        'vertices': vertices,
        'lanes': [[i, i+1, {'graph_idx': [2, 1], 'bidirectional': [4, True]}]
                  for i in range(5)],
        'walls': [[6, 7, {}]] if structural_wall else [],
        'doors': [[6, 7, {'name': [1, 'open_door']}]] if door else [],
    }
    return result


def derive_test(source, geometry=None):
    return derive(source, geometry or floor(), 0.1, 0.57, 0.40, 0.05)


def test_reference_png_artifacts_inside_approved_corridor_are_cleared():
    source = np.full((80, 100), 205, dtype=np.uint8)
    source[5, 5] = 0
    source[30, 20] = 255
    source[30, 40] = 0
    original = source.copy()
    derived, corrections, mask, _, report = derive_test(source)
    assert report['accepted']
    assert np.array_equal(source, original)
    assert derived[5, 5] == 0
    assert derived[30, 20] == 255
    assert derived[30, 25] == 254
    assert derived[30, 40] == 254
    assert corrections[30, 25] == CORRECTION_CODES['reference_unknown_to_free']
    assert corrections[30, 40] == CORRECTION_CODES['reference_occupied_to_free']
    assert derived[75, 90] == 205
    assert not np.any((derived != source) & ~mask)


def test_traffic_editor_wall_blocks_lane_and_is_enforced():
    source = np.full((80, 100), 205, dtype=np.uint8)
    derived, corrections, _, walls, report = derive_test(source, floor(structural_wall=True))
    assert not report['accepted']
    assert np.all(derived[walls] == 0)
    assert np.all(corrections[walls] == CORRECTION_CODES['traffic_editor_wall_enforced'])
    lane = report['lanes'][2]
    assert lane['building_lane_index'] == 2 and lane['building_vertices'] == [2, 3]
    assert lane['structural_wall_cells'] > 0


def test_open_door_segment_is_not_a_structural_obstacle():
    source = np.full((80, 100), 205, dtype=np.uint8)
    _, _, _, walls, report = derive_test(source, floor(door=True))
    assert report['accepted']
    assert not np.any(walls)


def test_approved_floor_polygon_becomes_known_but_walls_remain_occupied():
    source = np.full((80, 100), 205, dtype=np.uint8)
    geometry = floor()
    geometry['vertices'] += [
        [10, 15, 0, '', {}], [70, 15, 0, '', {}],
        [70, 45, 0, '', {}], [10, 45, 0, '', {}],
    ]
    geometry['floors'] = [{'vertices': [8, 9, 10, 11]}]
    geometry['walls'] = [[8, 9, {}]]
    areas = [{
        'name': 'test_known_area',
        'building': 'test.building.yaml',
        'floor_polygon_index': 0,
        'required_waypoints': ['husky_0'],
    }]
    derived, corrections, corridor, walls, report = derive(
        source, geometry, 0.1, 0.57, 0.40, 0.05, known_areas=areas)
    assert derived[20, 20] == 254
    assert not corridor[20, 20]
    assert corrections[20, 20] == CORRECTION_CODES['approved_area_unknown_to_free']
    assert report['changed_approved_area_unknown_to_free'] > 0
    assert report['known_areas'][0]['required_waypoints'] == ['husky_0']
    assert np.all(derived[walls] == 0)
    assert np.all(corrections[walls] == CORRECTION_CODES['traffic_editor_wall_enforced'])


def test_required_waypoints_use_incident_sweeps_and_graph_reachability():
    source = np.full((80, 100), 205, dtype=np.uint8)
    _, _, _, _, report = derive_test(source)
    assert report['required_waypoints']['husky_0']['incident_lane_indexes'] == [0]
    assert set(report['reachability']['reachable_required_waypoints']['husky_0']) == set(REQUIRED)


def test_out_of_image_corridor_fails():
    source = np.full((80, 100), 205, dtype=np.uint8)
    geometry = floor()
    geometry['vertices'][0][0] = 1
    _, _, _, _, report = derive_test(source, geometry)
    assert not report['accepted'] and report['lanes'][0]['out_of_bounds']


def setup_package(tmp_path, structural_wall=False):
    (tmp_path/'maps').mkdir()
    (tmp_path/'nav_graphs').mkdir()
    geometry = floor(structural_wall=structural_wall)
    geometry.update(measurements=[[0, 1, {'distance': [3, 1.0]}]],
                    drawing={'filename': 'brin_0.png'})
    building = {'coordinate_system': 'reference_image', 'levels': {'L1': geometry}}
    (tmp_path/'maps/brin_0.building.yaml').write_text(yaml.safe_dump(building))
    source = np.full((80, 100), 205, dtype=np.uint8)
    source[30, 40] = 0  # Reference-image artifact, not a Traffic Editor wall.
    Image.fromarray(source).save(tmp_path/'maps/brin_0.png')
    graph = {'levels': {'L1': {
        'vertices': [[vertex[0]*0.1, -vertex[1]*0.1, {'name': vertex[3]}]
                     for vertex in geometry['vertices']],
        'lanes': geometry['lanes']}}}
    (tmp_path/'nav_graphs/1.yaml').write_text(yaml.safe_dump(graph))
    policy = {
        'version': 1,
        'authority': {'reference_image': 'visual_reference',
                      'traffic_editor_walls': 'structural_obstacles',
                      'traffic_editor_doors': 'traversable_when_open'},
        'fleet_graph_index': 1,
        'clearance': {'additional_margin_m': 0.0, 'wall_thickness_m': 0.05},
    }
    (tmp_path/'maps/nav2_occupancy_policy.yaml').write_text(yaml.safe_dump(policy))
    config = tmp_path/'nav2.yaml'
    config.write_text(yaml.safe_dump({'local_costmap': {'local_costmap': {'ros__parameters': {
        'footprint': '[[-0.55, -0.38], [-0.55, 0.38], [0.55, 0.38], [0.55, -0.38]]',
        'footprint_padding': 0.02}}}}))
    generate(tmp_path/'maps/brin_0.building.yaml', tmp_path/'maps/brin_0.yaml')
    return config


def test_clear_candidate_is_promoted_and_independently_validated(tmp_path):
    config = setup_package(tmp_path)
    assert run(tmp_path, config)
    metadata = yaml.safe_load((tmp_path/'maps/brin_0.yaml').read_text())
    assert metadata['image'] == 'brin_0_nav2.png'
    result = audit(tmp_path, config)
    assert result['accepted']
    assert result['changed_reference_occupied_cells'] == 1


def test_structural_conflict_cannot_replace_live_metadata(tmp_path):
    config = setup_package(tmp_path, structural_wall=True)
    before = (tmp_path/'maps/brin_0.yaml').read_bytes()
    assert not run(tmp_path, config)
    assert (tmp_path/'maps/brin_0.yaml').read_bytes() == before
    assert not audit(tmp_path, config)['accepted']


def test_validator_rejects_candidate_edit_outside_policy(tmp_path):
    config = setup_package(tmp_path)
    assert run(tmp_path, config)
    candidate_path = tmp_path/'maps/brin_0_nav2.png'
    candidate = np.array(Image.open(candidate_path))
    candidate[75, 90] = 254
    Image.fromarray(candidate).save(candidate_path)
    with pytest.raises(ValueError, match='differs from policy-derived output'):
        audit(tmp_path, config)


def test_validator_rejects_tampered_correction_mask(tmp_path):
    config = setup_package(tmp_path)
    assert run(tmp_path, config)
    correction_path = tmp_path/'maps/brin_0_nav2_corrections.png'
    correction = np.array(Image.open(correction_path))
    correction[30, 40] = CORRECTION_CODES['unchanged']
    Image.fromarray(correction).save(correction_path)
    with pytest.raises(ValueError, match='Correction mask differs from policy'):
        audit(tmp_path, config)


def test_disconnected_additional_spawn_blocks_promotion():
    geometry = floor()
    geometry['vertices'][0][4]['spawn_robot_name'] = [1, 'husky_0']
    geometry['vertices'].append([80, 60, 0, 'new_charger', {'spawn_robot_name': [1, 'husky_6']}])
    source = np.full((80, 100), 205, dtype=np.uint8)
    _, _, _, _, report = derive_test(source, geometry)
    assert not report['accepted']
    assert report['reachability']['reachable_required_waypoints']['new_charger'] == []
