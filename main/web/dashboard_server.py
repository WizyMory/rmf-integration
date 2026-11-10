#!/usr/bin/env python3
"""Serve the built RMF dashboard with SPA routes, without a Node build at boot."""
import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from battery_store import BatteryStore, RosBatteryReader


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if urlsplit(self.path).path == '/brin/batteries':
            body = json.dumps(self.server.batteries.snapshot(), allow_nan=False).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def list_directory(self, path):
        self.send_error(403, 'Directory listing disabled')
        return None

    def send_head(self):
        route = unquote(urlsplit(self.path).path)
        target = Path(self.translate_path(self.path))
        if not target.exists() and not Path(route).suffix:
            self.path = '/index.html'
        return super().send_head()

    def end_headers(self):
        if urlsplit(self.path).path in ('/', '/index.html'):
            self.send_header('Cache-Control', 'no-cache')
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True)
    parser.add_argument('--host', default='192.168.0.141')
    parser.add_argument('--port', type=int, default=3000)
    parser.add_argument('--battery-ros', action='store_true')
    args = parser.parse_args()
    directory = Path(args.directory).resolve()
    if not (directory / 'index.html').is_file():
        parser.error('Build the dashboard before starting the server')
    handler = partial(DashboardHandler, directory=str(directory))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    server.batteries = BatteryStore()
    reader = RosBatteryReader(server.batteries) if args.battery_ros else None
    print(f'DASHBOARD_READY=http://{args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if reader is not None:
            reader.close()


if __name__ == '__main__':
    main()
