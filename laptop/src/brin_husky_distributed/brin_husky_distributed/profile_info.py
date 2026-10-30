"""Inspect map identity and named task destinations without connecting to ROS."""
import argparse
import json
import sys

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
    parser.add_argument('--choose-waypoint', action='store_true',
                        help='Prompt for a named waypoint and print only its name to stdout')
    options = parser.parse_args(args)
    profile = profile_info(options.traffic_profile)
    if not options.choose_waypoint:
        print(json.dumps(profile, indent=2))
        return
    if len(profile['places']) != 1:
        parser.error('Waypoint picker requires a profile with exactly one level')
    level, places = next(iter(profile['places'].items()))
    names = sorted(places)
    if not names:
        parser.error(f'No named waypoints on {level}')
    print(f'Named waypoints for {options.traffic_profile} ({level}):', file=sys.stderr)
    for number, name in enumerate(names, start=1):
        x, y = places[name]
        print(f'  {number}. {name} ({x:.2f}, {y:.2f})', file=sys.stderr)
    print('Choose an operator-approved waypoint by number or name: ',
          end='', file=sys.stderr, flush=True)
    selection = sys.stdin.readline().strip()
    if selection in places:
        chosen = selection
    elif selection.isdecimal() and 1 <= int(selection) <= len(names):
        chosen = names[int(selection) - 1]
    else:
        parser.error('Choose a listed waypoint; no task was sent')
    print(chosen)
