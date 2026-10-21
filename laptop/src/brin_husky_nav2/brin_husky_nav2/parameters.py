"""Resolve one reusable parameter template into a robot-specific YAML root."""
from pathlib import Path
import yaml
import re


def robot_parameters(path, namespace, use_sim_time=True, simulation_profile='fidelity'):
    if not re.fullmatch(r'husky_[0-9]+', namespace):
        raise ValueError(namespace)
    parameters = yaml.safe_load(Path(path).read_text().replace('__ROBOT__', namespace))

    if simulation_profile not in ('fast', 'fidelity'):
        raise ValueError(simulation_profile)
    if simulation_profile == 'fast':
        parameters['amcl']['ros__parameters'].update(
            min_particles=250, max_particles=1000, max_beams=60)
        parameters['bt_navigator']['ros__parameters']['bt_loop_duration'] = 50
        parameters['global_costmap']['global_costmap']['ros__parameters']['publish_frequency'] = 0.5
    # Preserve map/footprint, planner collision semantics and 0.4 m/s limits.
    def set_time(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'ros__parameters':
                    child['use_sim_time'] = use_sim_time
                set_time(child)
    set_time(parameters)
    return {namespace: parameters}
