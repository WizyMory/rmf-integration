"""Prepare a shared-map bringup without overwriting the working underlay."""
from copy import deepcopy
import math
from pathlib import Path
import yaml

from .profiles import load_settings, resolve_profile


def prepare_startup(share, localization_share, navigation_share, output_dir,
                    integration_config=None, fleet_config=None):
    share = Path(share)
    profile = resolve_profile(share)
    settings = load_settings(integration_config or share/'config/devi.yaml')
    fleet = yaml.safe_load(Path(fleet_config or share/'config/fleet_config.yaml').read_text())
    if fleet['robots'].keys() != {'devi'} or fleet['fleet_name'] != 'Devi':
        raise ValueError('Bringup requires only Devi/devi')
    startup = yaml.safe_load((share/'config/bringup.yaml').read_text())
    mode = startup['localization']
    if (startup['traffic_profile'] != 'gedungWS_0'
            or mode not in ('manual_initial_pose', 'automatic_initial_pose')):
        raise ValueError('Bringup requires gedungWS_0 and a supported localization mode')
    initial_pose = None
    if mode == 'automatic_initial_pose':
        pose = startup.get('initial_pose')
        if not isinstance(pose, dict) or pose.get('frame_id') != 'map':
            raise ValueError('Automatic initial pose requires frame_id map')
        initial_pose = {}
        for key in ('x', 'y', 'z', 'yaw'):
            value = pose.get(key)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value)):
                raise ValueError('Automatic initial pose requires finite numeric ' + key)
            initial_pose[key] = float(value)
    radius = startup['footprint_radius']
    if (isinstance(radius, bool) or not isinstance(radius, (float, int))
            or not math.isfinite(radius) or radius <= 0):
        raise ValueError('A positive physical footprint radius is required')
    fleet['profile']['footprint'] = float(radius)
    settings = deepcopy(settings)
    settings['nav2_map'] = profile['map_yaml']
    # This exact map/image/origin is the canonical RMF bundle, so conversion
    # is identity. Localization uses the configured startup pose or manual correction.
    settings['map_alignment'] = dict(confirmed=True, x=0., y=0., yaw=0.)
    settings['commissioning'] = deepcopy(startup['commissioning'])

    amcl = yaml.safe_load((Path(localization_share)/'config/amcl.yaml').read_text())
    amcl_parameters = amcl['amcl']['ros__parameters']
    if initial_pose is not None and amcl_parameters.get('global_frame_id', 'map') != 'map':
        raise ValueError('Automatic initial pose requires AMCL global_frame_id map')
    amcl_parameters.update(use_sim_time=False, set_initial_pose=initial_pose is not None,
                           always_reset_initial_pose=True)
    # The old map's (0,0,0) must never initialize the shared map.
    amcl_parameters.pop('initial_pose', None)
    if initial_pose is not None:
        amcl_parameters['initial_pose'] = initial_pose
    amcl['map_server']['ros__parameters'].update(
        use_sim_time=False, yaml_filename=profile['map_yaml'])

    nav2 = yaml.safe_load((Path(navigation_share)/'config/nav2_indoor.yaml').read_text())
    for name in ('local_costmap', 'global_costmap'):
        parameters = nav2[name][name]['ros__parameters']
        parameters.pop('footprint', None)
        parameters['robot_radius'] = float(radius)
        parameters['use_sim_time'] = False
    paths = {}
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    for name, contents in [('amcl', amcl), ('nav2', nav2), ('integration', settings), ('fleet', fleet)]:
        path = output/(name + '.yaml')
        # Atomic replacement: ROS processes never open a half-written YAML.
        temporary = path.with_suffix('.yaml.tmp')
        temporary.write_text(yaml.safe_dump(contents, sort_keys=False))
        temporary.replace(path)
        paths[name] = str(path)
    return {**paths, 'map': profile['map_yaml'], 'graph': profile['graph'],
            'profile_digest': profile['digest']}
