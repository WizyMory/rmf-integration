#!/usr/bin/env python3
"""Bounded readiness checks for the main computer's boot services."""
import argparse
import ipaddress
import json
import os
import subprocess
import time
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=('network', 'http'))
    parser.add_argument('url', nargs='?')
    parser.add_argument('--timeout', type=float, default=90)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 180:
        parser.error('timeout must be between 1 and 180 seconds')
    if args.kind == 'http' and not args.url:
        parser.error('http requires a URL')
    deadline = time.monotonic() + args.timeout
    last_error = ''
    while time.monotonic() < deadline:
        try:
            if args.kind == 'http':
                with urllib.request.urlopen(args.url, timeout=3) as response:
                    if response.status == 200:
                        print('HTTP_READY=' + args.url, flush=True)
                        return 0
            else:
                interface = os.environ.get('BRIN_MAIN_INTERFACE', 'enp7s0')
                address = str(ipaddress.IPv4Address(os.environ.get('BRIN_MAIN_IP', '192.168.0.141')))
                result = subprocess.run(['ip', '-json', 'address', 'show', 'dev', interface],
                                        capture_output=True, text=True, timeout=3)
                records = json.loads(result.stdout or '[]')
                if any('UP' in record.get('flags', []) and any(
                        entry.get('local') == address for entry in record.get('addr_info', []))
                       for record in records):
                    print('NETWORK_READY=' + interface + ' ' + address, flush=True)
                    return 0
        except (OSError, ValueError, subprocess.TimeoutExpired, urllib.error.URLError) as error:
            last_error = str(error)
        time.sleep(1)
    print('READINESS_TIMEOUT=' + args.kind + ' ' + last_error, flush=True)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
