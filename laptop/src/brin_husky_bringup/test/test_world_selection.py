import importlib.util
from pathlib import Path
import pytest


ROOT = Path(__file__).resolve().parents[2]


def load_launch():
    path = ROOT/'brin_husky_bringup/launch/simulation.launch.py'
    spec = importlib.util.spec_from_file_location('simulation_launch', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_packaged_world_selection_preserves_brin_spawn_world():
    module = load_launch()
    worlds = ROOT/'brin_rmf_maps'
    assert module.resolve_world(worlds, 'brin.sdf') == worlds/'worlds/brin.sdf'
    assert module.resolve_world(worlds, 'brin_dynamic_pedestrian.sdf') == (
        worlds/'worlds/brin_dynamic_pedestrian.sdf')


def test_world_selection_rejects_wrong_world_and_unsafe_relative_path(tmp_path):
    module = load_launch()
    with pytest.raises(ValueError, match='packaged SDF filename'):
        module.resolve_world(tmp_path, '../brin.sdf')
    invalid = tmp_path/'other.sdf'
    invalid.write_text('<sdf version="1.7"><world name="other"><physics><max_step_size>0.01</max_step_size></physics></world></sdf>')
    with pytest.raises(ValueError, match='world named brin'):
        module.resolve_world(tmp_path, str(invalid))
