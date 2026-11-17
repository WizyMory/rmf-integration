"""Offline configuration, asset pinning and coordinate conversion."""
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

import yaml


class ConfigError(ValueError):
    pass


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def load(path, commissioned=False, pinned=True, require_profile=True):
    path = Path(path).resolve()
    try:
        config = yaml.safe_load(path.read_text())
        if not isinstance(config, dict) or config.get('version') != 1:
            raise ConfigError('version must be 1')
        for section in ('robot', 'rmf', 'nav2', 'geometry', 'motion', 'alignment', 'commissioning'):
            if not isinstance(config.get(section), dict):
                raise ConfigError('Missing mapping: '+section)
        robot, core, nav = config['robot'], config['rmf'], config['nav2']
        for label, value in [('robot.name', robot.get('name')), ('robot.fleet', robot.get('fleet'))]:
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', value):
                raise ConfigError(label+' must be an identifier, e.g. robot_01')
        for name, section in [('rmf', core), ('nav2', nav)]:
            domain = section.get('domain_id')
            if type(domain) is not int or not 0 <= domain <= 232:
                raise ConfigError(name+'.domain_id must be 0..232')
            if section.get('rmw') not in ('rmw_cyclonedds_cpp', 'rmw_fastrtps_cpp'):
                raise ConfigError(name+'.rmw must be rmw_cyclonedds_cpp or rmw_fastrtps_cpp')
            if type(section.get('localhost_only', False)) is not bool:
                raise ConfigError(name+'.localhost_only must be a YAML boolean')
            for key in ('cyclonedds_uri', 'fastdds_profiles_file', 'discovery_server'):
                if not isinstance(section.get(key, ''), str):
                    raise ConfigError(name+'.'+key+' must be a string')
            if section.get('cyclonedds_uri', ''):
                uri = section['cyclonedds_uri']
                if not uri.startswith('file://'):
                    raise ConfigError(name+'.cyclonedds_uri must use file:///absolute/path')
                if not Path(uri[7:]).is_file():
                    raise ConfigError('DDS XML does not exist: '+uri[7:])
            if section.get('fastdds_profiles_file') and not Path(section['fastdds_profiles_file']).is_file():
                raise ConfigError('Fast DDS profiles file does not exist')
        for key in ('map_frame', 'base_frame'):
            if not isinstance(nav.get(key), str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_/]*', nav[key]):
                raise ConfigError('nav2.'+key+' must be a TF frame without a leading slash')
        for key in ('planner_id', 'controller_id'):
            if not isinstance(nav.get(key), str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', nav[key]):
                raise ConfigError('nav2.'+key+' must match the installed Nav2 plugin ID')
        topics = ('navigate_action', 'bt_navigator_node', 'map_topic', 'scan_topic', 'odom_topic', 'tf_topic', 'tf_static_topic')
        for key in topics:
            if not isinstance(nav.get(key), str) or not re.fullmatch(r'/[A-Za-z0-9_/]+', nav[key]):
                raise ConfigError('nav2.'+key+' must be an absolute ROS name')
        lifecycle = nav.get('lifecycle_nodes')
        if not isinstance(lifecycle, list) or not lifecycle or len(set(lifecycle)) != len(lifecycle):
            raise ConfigError('nav2.lifecycle_nodes must contain unique fully qualified node names')
        if not all(isinstance(n, str) and re.fullmatch(r'/[A-Za-z0-9_/]+', n) for n in lifecycle):
            raise ConfigError('nav2.lifecycle_nodes contains an invalid ROS name')
        for key in ('max_data_age', 'max_graph_distance', 'update_hz', 'action_timeout'):
            if not positive(nav.get(key)):
                raise ConfigError('nav2.'+key+' must be a positive finite number')
        if not 1 <= nav['update_hz'] <= 20 or not 1 <= nav['action_timeout'] <= 120:
            raise ConfigError('update_hz must be 1..20; action_timeout 1..120 seconds')
        for key in ('footprint_radius', 'vicinity_radius'):
            if not positive(config['geometry'].get(key)):
                raise ConfigError('geometry.'+key+' must be measured and positive (metres)')
        if config['geometry']['vicinity_radius'] < config['geometry']['footprint_radius']:
            raise ConfigError('vicinity_radius must be >= footprint_radius')
        for key in ('linear_speed', 'linear_acceleration', 'angular_speed', 'angular_acceleration'):
            if not positive(config['motion'].get(key)):
                raise ConfigError('motion.'+key+' must be measured and positive')
        if config['motion'].get('reversible') is not False:
            raise ConfigError('This release supports reversible: false only')
        for key in ('x', 'y', 'yaw'):
            value = config['alignment'].get(key)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ConfigError('alignment.'+key+' must be finite (metres/radians)')
        for section, key in [(core, 'nav_graph'), (core, 'building_map'), (nav, 'map_yaml')]:
            if not isinstance(section.get(key), str) or not section[key]:
                raise ConfigError(key+' must be a path relative to robot.yaml or an absolute path')
            section[key] = str((path.parent/section[key]).resolve())
            if not Path(section[key]).is_file():
                raise ConfigError('Missing asset: '+section[key])
        graph = yaml.safe_load(Path(core['nav_graph']).read_text())
        level = graph['levels'][core['level']]
        vertices, lanes = level['vertices'], level['lanes']
        if not vertices or not isinstance(lanes, list):
            raise ConfigError('Graph requires vertices and lanes on the configured RMF level')
        names = [v[2].get('name') for v in vertices if len(v) >= 3 and v[2].get('name')]
        if len(set(names)) != len(names) or core.get('home_waypoint') not in names:
            raise ConfigError('Graph waypoint names must be unique and include rmf.home_waypoint')
        if not any(len(v) >= 3 and v[2].get('name') == core['home_waypoint']
                   and v[2].get('is_charger') is True for v in vertices):
            raise ConfigError('RMF Humble requires home_waypoint to have is_charger: true in the canonical graph; automatic charging stays disabled')
        for vertex in vertices:
            if len(vertex) < 2 or not all(type(v) in (int, float) and math.isfinite(v) for v in vertex[:2]):
                raise ConfigError('Graph vertices require finite XY')
        for lane in lanes:
            if len(lane) < 2 or any(type(i) is not int or not 0 <= i < len(vertices) for i in lane[:2]):
                raise ConfigError('Graph lane references an invalid vertex')
        if type(nav.get('final_orientation_only')) is not bool:
            raise ConfigError('nav2.final_orientation_only must be a YAML boolean')
        if nav['final_orientation_only']:
            if nav.get('transit_params_confirmed') is not True:
                raise ConfigError('Review and load the rendered Nav2 transit parameters; set transit_params_confirmed: true')
            if not positive(nav.get('transit_xy_tolerance')):
                raise ConfigError('Transit requires a positive transit_xy_tolerance')
        uri = core.get('web_uri', '')
        parsed = urlsplit(uri)
        if uri and (parsed.scheme not in ('ws', 'wss') or not parsed.hostname or parsed.username or parsed.password):
            raise ConfigError('rmf.web_uri must be empty or a ws(s) URL without credentials')
        if not isinstance(core.get('profile_topic'), str) or not core['profile_topic'].startswith('/'):
            raise ConfigError('rmf.profile_topic must be absolute')
        if require_profile and not re.fullmatch('[a-f0-9]{64}', core.get('expected_profile_digest', '') or ''):
            raise ConfigError('rmf.expected_profile_digest must be the 64-character SHA256 from the core')
        battery = config.get('battery', {'mode': 'none'})
        if battery.get('mode') not in ('none', 'battery_state', 'voltage'):
            raise ConfigError('battery.mode must be none, battery_state or voltage')
        if battery['mode'] != 'none':
            if not isinstance(battery.get('topic'), str) or not battery['topic'].startswith('/'):
                raise ConfigError('battery.topic must be absolute')
        if battery['mode'] == 'voltage':
            if not positive(battery.get('empty_voltage')) or not positive(battery.get('full_voltage')) or battery['full_voltage'] <= battery['empty_voltage']:
                raise ConfigError('Battery calibration requires full_voltage > empty_voltage > 0')
        config['battery'] = battery
        if commissioned:
            for key in ('alignment_confirmed', 'footprint_confirmed', 'nav2_motion_tested', 'operation_accepted'):
                if config['commissioning'].get(key) is not True:
                    raise ConfigError('Commissioning pending: '+key)
        config['_path'] = str(path)
        config['_vertices'], config['_lanes'] = vertices, lanes
        if pinned:
            lock = json.loads(path.with_name('assets.lock.json').read_text())
            if lock != asset_hashes(config):
                raise ConfigError('Asset lock mismatch; review copied site assets and run pin-assets again')
        return config
    except ConfigError:
        raise
    except (OSError, ValueError, TypeError, KeyError, IndexError, yaml.YAMLError) as exc:
        raise ConfigError(str(exc)) from exc


def asset_hashes(config):
    metadata_path = Path(config['nav2']['map_yaml'])
    metadata = yaml.safe_load(metadata_path.read_text())
    if (not positive(metadata.get('resolution')) or len(metadata.get('origin', [])) != 3
            or not all(type(value) in (int, float) and math.isfinite(value) for value in metadata['origin'])
            or not isinstance(metadata.get('image'), str)):
        raise ConfigError('Map YAML requires positive resolution and origin [x,y,yaw]')
    image = (metadata_path.parent/metadata['image']).resolve()
    return {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in (
        ('nav_graph', Path(config['rmf']['nav_graph'])), ('building_map', Path(config['rmf']['building_map'])),
        ('map_yaml', metadata_path), ('map_image', image))}


def site_digest(config):
    return hashlib.sha256(json.dumps(asset_hashes(config), sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def environment(section):
    """Explicit per-process DDS configuration, without editing an underlay."""
    return {'ROS_DOMAIN_ID': str(section['domain_id']),
            'ROS_LOCALHOST_ONLY': '1' if section.get('localhost_only', False) else '0',
            'RMW_IMPLEMENTATION': section['rmw'],
            'CYCLONEDDS_URI': section.get('cyclonedds_uri', ''),
            'FASTRTPS_DEFAULT_PROFILES_FILE': section.get('fastdds_profiles_file', ''),
            'FASTDDS_DEFAULT_PROFILES_FILE': section.get('fastdds_profiles_file', ''),
            'ROS_DISCOVERY_SERVER': section.get('discovery_server', '')}


class Alignment:
    def __init__(self, config):
        self.x, self.y, self.yaw = (float(config[k]) for k in ('x', 'y', 'yaw'))
        self.c, self.s = math.cos(self.yaw), math.sin(self.yaw)

    def to_rmf(self, pose):
        x, y, yaw = pose
        return [self.c*x-self.s*y+self.x, self.s*x+self.c*y+self.y, self.wrap(yaw+self.yaw)]

    def to_nav2(self, pose):
        x, y, yaw = pose
        x, y = x-self.x, y-self.y
        return [self.c*x+self.s*y, -self.s*x+self.c*y, self.wrap(yaw-self.yaw)]

    @staticmethod
    def wrap(yaw):
        return math.atan2(math.sin(yaw), math.cos(yaw))


def distance_to_graph(config, pose):
    vertices = config['_vertices']
    distances = [math.hypot(v[0]-pose[0], v[1]-pose[1]) for v in vertices]
    for source, target, *_ in config['_lanes']:
        a, b = vertices[source], vertices[target]
        dx, dy = b[0]-a[0], b[1]-a[1]
        length = dx*dx+dy*dy
        u = max(0., min(1., ((pose[0]-a[0])*dx+(pose[1]-a[1])*dy)/length)) if length else 0.
        distances.append(math.hypot(pose[0]-a[0]-u*dx, pose[1]-a[1]-u*dy))
    return min(distances)
