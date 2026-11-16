"""Prepare startup AMCL parameters from the installed physical Nav2 configuration."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import yaml

from brin_husky_distributed.profiles import resolve_profile
from brin_husky_distributed.web_runtime import validate_server_uri


def load_settings(path):
    settings = yaml.safe_load(Path(path).read_text())
    if not isinstance(settings, dict) or settings.get('traffic_profile') != 'gedungWS_0':
        raise ValueError('The commissioned startup pose requires traffic_profile gedungWS_0')
    pose = settings.get('initial_pose', {})
    if pose.get('frame_id') != 'map':
        raise ValueError('Initial pose frame_id must be map')
    for key in ('x', 'y', 'z', 'yaw'):
        value = pose.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError('Initial pose requires finite numeric ' + key)
    validate_server_uri(settings.get('server_uri', ''), remote=True)
    distance = settings.get('startup_graph_distance')
    if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not 1.0 <= distance <= 1.25:
        raise ValueError('Startup graph distance must be within the approved 1.00..1.25 m range')
    for key in ('scan_timeout', 'navigation_timeout', 'preflight_timeout', 'retry_delay'):
        value = settings.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 1 <= value <= 600:
            raise ValueError('Invalid positive startup duration: ' + key)
    return settings


def prepare(settings, nav2_source, output_dir, maps_share=None, *, hardware_source, fleet_source):
    profile = resolve_profile(settings['traffic_profile'], maps_share)
    source = Path(nav2_source)
    parameters = yaml.safe_load(source.read_text())
    generated = deepcopy(parameters)
    amcl = generated['amcl']['ros__parameters']
    if amcl.get('global_frame_id') != 'map':
        raise ValueError('Installed physical AMCL must use map frame')
    if amcl.get('use_sim_time', False) is not False:
        raise ValueError('Physical AMCL cannot use simulation time')
    amcl.update(set_initial_pose=True, always_reset_initial_pose=True,
                initial_pose={key: float(settings['initial_pose'][key])
                              for key in ('x', 'y', 'z', 'yaw')})
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output/'nav2_startup.yaml'
    temporary = path.with_suffix('.yaml.tmp')
    temporary.write_text(yaml.safe_dump(generated, sort_keys=False))
    temporary.replace(path)
    hardware = yaml.safe_load(Path(hardware_source).read_text())
    fleet = yaml.safe_load(Path(profile.get('fleet_config', fleet_source)).read_text())
    hardware['max_graph_distance'] = float(settings['startup_graph_distance'])
    fleet['max_merge_lane_distance'] = float(settings['startup_graph_distance'])
    for name, data in (('hardware_startup', hardware), ('fleet_startup', fleet)):
        target = output/(name+'.yaml')
        temporary = target.with_suffix('.yaml.tmp')
        temporary.write_text(yaml.safe_dump(data, sort_keys=False))
        temporary.replace(target)
    result = {'nav2_source': str(source), 'nav2_source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'params_file': str(path), 'map': str(profile['map_yaml']),
              'traffic_profile': settings['traffic_profile'], 'profile_digest': profile['digest'],
              'server_uri': settings.get('server_uri', ''), 'initial_pose': settings['initial_pose'],
              'hardware_config': str(output/'hardware_startup.yaml'),
              'startup_fleet_config': str(output/'fleet_startup.yaml'),
              'startup_graph_distance': settings['startup_graph_distance']}
    (output/'prepared.json').write_text(json.dumps(result, indent=2)+'\n')
    return result
