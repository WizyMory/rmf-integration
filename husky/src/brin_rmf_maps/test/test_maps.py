from pathlib import Path
import sys
import yaml
import xml.etree.ElementTree as ET
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from map_geometry import image_to_map, load_geometry
from validate_map_alignment import validate


def test_alignment():
    assert max(validate(ROOT/'maps/brin_0.building.yaml', ROOT/'nav_graphs/1.yaml',
                        ROOT/'maps/brin_0.yaml', allow_derived=True).values()) <= 0.10


def test_bad_origin_is_rejected(tmp_path):
    metadata = yaml.safe_load((ROOT/'maps/brin_0.yaml').read_text())
    metadata['image'] = str(ROOT/'maps/brin_0.png')
    metadata['origin'][1] += 1.0
    bad = tmp_path/'bad.yaml'
    bad.write_text(yaml.safe_dump(metadata))
    with pytest.raises(ValueError, match='exceeds'):
        validate(ROOT/'maps/brin_0.building.yaml', ROOT/'nav_graphs/1.yaml', bad)


def test_world_has_no_placeholder_robots_or_doors():
    world = ET.parse(ROOT/'worlds/brin.sdf').getroot().find('world')
    assert world.get('name') == 'brin'
    text = ET.tostring(world).decode()
    assert 'HuskyA200' not in text
    model_names = [m.get('name') for m in world.findall('model')]
    model_names += [m.findtext('name') for m in world.findall('include')]
    assert 'husky_0' not in model_names and 'husky_1' not in model_names
    assert not world.findall('.//door')


def test_world_contains_profile_simulation_models():
    building = yaml.safe_load((ROOT/'maps/banyak_simpangan.building.yaml').read_text())
    expected = building['levels']['L1']['models']
    _, _, _, _, scale, _ = load_geometry(ROOT/'maps/banyak_simpangan.building.yaml')
    world = ET.parse(ROOT/'worlds/brin.sdf').getroot().find('world')
    includes = {include.findtext('name'): include for include in world.findall('include')}
    instance_counts = {}
    generated_names = []
    for model in expected:
        base = model['name']
        instance_counts[base] = instance_counts.get(base, 0)+1
        number = instance_counts[base]
        generated_names.append(base if number == 1 else f'{base}_{number}')
    model_assets = {model['model_name'].rsplit('/', 1)[-1] for model in expected}
    simulation_includes = {
        name: include for name, include in includes.items()
        if include.findtext('uri').removeprefix('model://') in model_assets
    }
    assert len(expected) == len(generated_names) == len(simulation_includes)
    for model, generated_name in zip(expected, generated_names):
        include = includes[generated_name]
        asset = model['model_name'].rsplit('/', 1)[-1]
        assert include.findtext('uri') == f'model://{asset}'
        assert include.findtext('static').lower() == 'true'
        pose = [float(value) for value in include.findtext('pose').split()]
        assert pose[:2] == pytest.approx(image_to_map(model['x'], model['y'], scale))
        assert pose[2] == pytest.approx(model['z'])
        assert pose[5] == pytest.approx(model['yaw'])
    assert set(generated_names) == set(simulation_includes)
    for asset in model_assets:
        local_model = ET.parse(ROOT/f'models/{asset}/model.sdf').getroot().find('model')
        assert local_model.findtext('static').lower() == 'true'
        assert local_model.find('.//collision') is not None
        uris = [element.text for element in local_model.findall('.//uri')]
        assert uris and all(uri.startswith(f'model://{asset}/') for uri in uris)


def test_dynamic_pedestrian_has_synchronized_physics_body():
    world = ET.parse(ROOT/'worlds/brin_dynamic_pedestrian.sdf').getroot().find('world')
    assert world.get('name') == 'brin'
    actor = world.find("actor[@name='pedestrian_crossing_01']")
    collider = world.find("model[@name='pedestrian_crossing_01_collision']")
    plugin = world.find("plugin[@name='brin_rmf_maps::ActorCollisionFollower']")
    assert actor is not None and collider is not None and plugin is not None
    assert collider.findtext('static') == 'true'
    assert collider.find('.//collision/geometry/cylinder') is not None
    assert float(collider.findtext('.//collision/geometry/cylinder/radius')) == pytest.approx(0.28)
    assert float(collider.findtext('.//collision/geometry/cylinder/length')) == pytest.approx(1.6)
    assert plugin.findtext('actor_name') == actor.get('name')
    assert plugin.findtext('collision_model_name') == collider.get('name')
    assert plugin.get('filename') == 'libbrin_actor_collision_follower.so'
    times = [float(point.findtext('time')) for point in actor.findall('script/trajectory/waypoint')]
    assert times == [0, 4, 5, 9, 10]


def test_active_map_keeps_promoted_occupancy_image():
    metadata = yaml.safe_load((ROOT/'maps/brin_0.yaml').read_text())
    assert metadata['image'] == 'brin_0_nav2.png'


def test_spawn_manifest_matches_editor_and_fleet():
    from map_geometry import graph_spawns
    building = yaml.safe_load((ROOT/'maps/brin_0.building.yaml').read_text())
    expected = {v[4]['spawn_robot_name'][1]: v[3]
                for v in building['levels']['L1']['vertices']
                if len(v) > 4 and 'spawn_robot_name' in v[4]}
    spawns = graph_spawns(ROOT/'nav_graphs/1.yaml')
    assert set(spawns) == set(expected) == {f'husky_{i}' for i in range(7)}
    assert yaml.safe_load((ROOT/'maps/spawns.yaml').read_text()) == spawns
    fleet = yaml.safe_load((ROOT.parent/'brin_husky_fleet_adapter/config/fleet_config.yaml').read_text())
    assert {name: pose['charger'] for name, pose in spawns.items()} == expected
    assert {name: c['charger'] for name, c in fleet['robots'].items()} == expected


def test_duplicate_spawn_is_rejected(tmp_path):
    from map_geometry import graph_spawns
    graph = yaml.safe_load((ROOT/'nav_graphs/1.yaml').read_text())
    vertices = graph['levels']['L1']['vertices']
    duplicate = next(vertex for vertex in vertices
                     if vertex[2].get('spawn_robot_name')
                     and vertex[2]['spawn_robot_name'] != 'husky_0')
    duplicate[2]['spawn_robot_name'] = 'husky_0'
    path = tmp_path/'graph.yaml'
    path.write_text(yaml.safe_dump(graph))
    with pytest.raises(ValueError, match='duplicate'):
        graph_spawns(path)


def test_registered_traffic_profiles_are_complete_and_accepted():
    import json
    profiles = yaml.safe_load((ROOT/'maps/traffic_profiles.yaml').read_text())
    assert profiles['default_profile'] == 'brin_0'
    assert set(profiles['profiles']) == {'brin_0', 'banyak_simpangan', 'gedungWS_0'}
    for profile in profiles['profiles'].values():
        assert (ROOT/'maps'/profile['building_map']).is_file()
        assert (ROOT/'nav_graphs'/profile['nav_graph']).is_file()
        assert (ROOT/'maps'/profile['nav2_map']).is_file()
        if 'fleet_config' in profile:
            assert (ROOT/'maps'/profile['fleet_config']).is_file()
    graph = yaml.safe_load((ROOT/'nav_graphs/banyak_simpangan.yaml').read_text())
    assert all('door_name' not in lane[2]
               for level in graph['levels'].values() for lane in level['lanes'])
    report = json.loads((ROOT/'maps/banyak_simpangan_occupancy_report.json').read_text())
    assert report['accepted'] and report['promoted']
    assert not [lane for lane in report['lanes'] if not lane['accepted']]


def test_gedungws_map_graph_and_charger_are_registered_together():
    from PIL import Image
    import numpy as np
    building = yaml.safe_load((ROOT/'maps/gedungWS_0.building.yaml').read_text())
    derived = yaml.safe_load((ROOT/'maps/gedungWS_0_rmf.building.yaml').read_text())
    native = yaml.safe_load((ROOT/'maps/gedungWS_0.yaml').read_text())
    active = yaml.safe_load((ROOT/'maps/gedungWS_0_rmf.yaml').read_text())
    graph = yaml.safe_load((ROOT/'nav_graphs/gedungWS_0.yaml').read_text())
    fleet = yaml.safe_load((ROOT/'maps/gedungWS_0_fleet.yaml').read_text())
    report = __import__('json').loads((ROOT/'maps/gedungWS_0_report.json').read_text())
    assert set(building['levels']) == {'gedungWS_lt1'}
    assert set(derived['levels']) == set(graph['levels']) == {'L1'}
    assert fleet['map_name'] == 'L1'
    assert fleet['robots']['husky_0']['charger'] == 'ws_p0'
    assert not report['blocked_footprint_sweeps']
    with Image.open(ROOT/'maps'/native['image']) as source, \
            Image.open(ROOT/'maps'/active['image']) as target:
        assert np.array_equal(np.asarray(source), np.asarray(target))
        assert active['origin'] == [0.0, -source.height*active['resolution'], 0.0]
    names = {v[2].get('name') for v in graph['levels']['L1']['vertices']}
    assert {'ws_p0', 'utara_WS', 'selatan_WS'} <= names


def test_profile_graph_preserves_passthrough_points():
    building = yaml.safe_load(
        (ROOT/'maps/banyak_simpangan.building.yaml').read_text())
    _, _, _, _, scale, _ = load_geometry(
        ROOT/'maps/banyak_simpangan.building.yaml')
    expected = []
    for vertex in building['levels']['L1']['vertices']:
        properties = vertex[4] if len(vertex) > 4 else {}
        if 'is_passthrough_point' in properties:
            x, y = image_to_map(vertex[0], vertex[1], scale)
            expected.append((x, y, properties['is_passthrough_point'][1]))

    graph = yaml.safe_load(
        (ROOT/'nav_graphs/banyak_simpangan.yaml').read_text())
    actual = [vertex for vertex in graph['levels']['L1']['vertices']
              if 'is_passthrough_point' in vertex[2]]
    assert len(actual) == len(expected)
    for x, y, value in expected:
        matches = [vertex for vertex in actual
                   if abs(vertex[0]-x) < 1e-9 and abs(vertex[1]-y) < 1e-9]
        assert len(matches) == 1
        assert matches[0][2]['is_passthrough_point'] is value
