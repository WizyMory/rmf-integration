"""Inspect map identity and named task destinations without connecting to ROS."""
import argparse
import json

import yaml

from .profiles import resolve_profile


def profile_info(name):
    profile = resolve_profile(name)
    graph = yaml.safe_load(profile['graph'].read_text())
    places = {
        level: {vertex[2]['name']: vertex[:2]
                for vertex in contents['vertices'] if vertex[2].get('name')}
        for level, contents in graph['levels'].items()
    }
    return {**{key: str(value) for key, value in profile.items()}, 'places': places}


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--traffic-profile', default='banyak_simpangan')
    options = parser.parse_args(args)
    print(json.dumps(profile_info(options.traffic_profile), indent=2))
