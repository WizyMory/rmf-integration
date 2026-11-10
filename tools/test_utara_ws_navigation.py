"""Offline regression: every physical fleet must navigate the final lane.

No ROS node, action client, task submission or physical goal is created here.
"""
from datetime import datetime
import copy
import importlib.util
from pathlib import Path
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
BUNDLES = [ROOT / 'laptop/src/brin_rmf_maps',
           ROOT / 'husky/src/brin_rmf_maps',
           ROOT / 'devi/src/brin_devi_fleet_adapter']


@pytest.mark.parametrize('bundle', BUNDLES, ids=['laptop-main', 'husky', 'devi'])
def test_utara_final_lane_is_ordinary_navigation(bundle):
    level = yaml.safe_load((bundle / 'nav_graphs/gedungWS_0.yaml').read_text())['levels']['L1']
    target, = [i for i, v in enumerate(level['vertices']) if v[2].get('name') == 'utara_WS']
    incoming = [lane for lane in level['lanes'] if lane[1] == target]
    outgoing = [lane for lane in level['lanes'] if lane[0] == target]
    assert incoming and outgoing
    assert len(level['vertices']) == 19 and len(level['lanes']) == 38
    assert level['vertices'][target][:2] == pytest.approx([1.7381, -27.2952])
    assert level['vertices'][target][2]['is_charger'] is True
    for properties in [level['vertices'][target][2], *(lane[2] for lane in incoming + outgoing)]:
        assert not {'dock_name', 'undock_name'} & properties.keys()


@pytest.mark.parametrize('bundle', BUNDLES, ids=['laptop-main', 'husky', 'devi'])
def test_derived_building_cannot_reintroduce_unsupported_docking(bundle):
    level = yaml.safe_load((bundle / 'maps/gedungWS_0_rmf.building.yaml').read_text())['levels']['L1']
    target, = [v for v in level['vertices'] if v[3] == 'utara_WS']
    assert target[:2] == pytest.approx([34.762, 545.904])
    assert 'dock_name' not in target[4]


@pytest.mark.parametrize('bundle', BUNDLES, ids=['laptop-main', 'husky', 'devi'])
def test_native_rmf_plans_reach_utara_without_docking_event(bundle):
    pytest.importorskip('rmf_adapter')
    from rmf_adapter import geometry, graph, plan, vehicletraits as traits

    profile = traits.Profile(geometry.make_final_convex_circle(.55),
                             geometry.make_final_convex_circle(.8))
    vehicle = traits.VehicleTraits(traits.Limits(.5, .3), traits.Limits(.5, .5), profile)
    vehicle.differential.reversible = False
    native = graph.parse_graph(str(bundle / 'nav_graphs/gedungWS_0.yaml'), vehicle)
    target = native.find_waypoint('utara_WS')
    planner = plan.Planner(plan.Configuration(native, vehicle))
    data = yaml.safe_load((bundle / 'nav_graphs/gedungWS_0.yaml').read_text())
    origins = [v[2]['name'] for v in data['levels']['L1']['vertices']
               if v[2].get('name') and v[2]['name'] != 'utara_WS']
    assert len(origins) == 7
    for name in origins:
        waypoints = planner.get_plan_waypoints(
            plan.Start(datetime(2026, 11, 10), native.find_waypoint(name).index, 0.),
            plan.Goal(target.index))
        assert waypoints, name
        assert waypoints[-1].graph_index == target.index, name
        assert list(waypoints[-1].position[:2]) == pytest.approx([1.7381, -27.2952])
        assert all(waypoint.event is None for waypoint in waypoints), name


def load_generator(package):
    path = str(package / 'tools')
    sys.path.insert(0, path)
    try:
        spec = importlib.util.spec_from_file_location(
            'utara_gedungws_generator', package / 'tools/generate_gedungws.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(path)


@pytest.mark.parametrize('package', BUNDLES[:2], ids=['laptop-main', 'husky'])
def test_generator_removes_only_unsupported_dock_annotations(package):
    module = load_generator(package)
    source = yaml.safe_load((package / 'maps/gedungWS_0.building.yaml').read_text())
    original = source['levels']['gedungWS_lt1']
    floor = copy.deepcopy(original)
    assert module.navigation_only_docks(floor) == ['utara']
    # Source editor input and every other navigation/task property survive.
    target, = [v for v in original['vertices'] if v[3] == 'utara_WS']
    assert target[4]['dock_name'] == [1, 'utara']
    restored = copy.deepcopy(floor)
    derived_target, = [v for v in restored['vertices'] if v[3] == 'utara_WS']
    derived_target[4]['dock_name'] = [1, 'utara']
    assert restored == original
    assert module.navigation_only_docks(floor) == []  # idempotent


def test_generator_also_removes_explicit_dock_and_undock_lane_annotations():
    module = load_generator(BUNDLES[0])
    floor = {'vertices': [[0., 0., 0, 'start'], [1., 0., 0, 'end', {'is_charger': [4, True]}]],
             'lanes': [[0, 1, {'dock_name': [1, 'dock'], 'speed_limit': [3, .2]}],
                       [1, 0, {'undock_name': [1, 'dock'], 'speed_limit': [3, .2]}]]}
    assert module.navigation_only_docks(floor) == ['dock']
    assert all(lane[2] == {'speed_limit': [3, .2]} for lane in floor['lanes'])
    assert floor['vertices'][1][4] == {'is_charger': [4, True]}


@pytest.mark.parametrize('package', BUNDLES[:2], ids=['laptop-main', 'husky'])
def test_fresh_generation_matches_shipped_bundle_without_changing_inputs(package, tmp_path):
    import shutil

    # The existing generator and building_map_generator run offline in staging.
    # Never regenerate directly over a live install or robot configuration.
    staging = tmp_path / 'brin_rmf_maps'
    (staging / 'maps').mkdir(parents=True)
    (staging / 'nav_graphs').mkdir()
    config_dir = tmp_path / 'brin_husky_distributed/config'
    config_dir.mkdir(parents=True)
    shutil.copy2(package.parent / 'brin_husky_distributed/config/fleet_config.yaml',
                 config_dir / 'fleet_config.yaml')
    for name in ('gedungWS_0.building.yaml', 'gedungWS_0.yaml', 'gedungWS_0.png', 'gedungWS_0.pgm'):
        shutil.copy2(package / 'maps' / name, staging / 'maps' / name)
    original = (staging / 'maps/gedungWS_0.building.yaml').read_bytes()
    module = load_generator(package)
    module.generate(staging, ROOT / 'husky/src/husky_nav2/config/nav2_params.yaml')
    assert (staging / 'maps/gedungWS_0.building.yaml').read_bytes() == original
    for name in ('maps/gedungWS_0_rmf.building.yaml', 'nav_graphs/gedungWS_0.yaml',
                 'maps/gedungWS_0_rmf.yaml', 'maps/gedungWS_0_fleet.yaml',
                 'maps/gedungWS_0_report.json'):
        assert (staging / name).read_bytes() == (package / name).read_bytes(), name
