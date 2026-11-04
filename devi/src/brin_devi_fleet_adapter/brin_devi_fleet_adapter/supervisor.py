"""Wait for Nav2 localization and the laptop core, then start one adapter."""
import argparse
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import time
import sys

from ament_index_python.packages import get_package_prefix
from rclpy.utilities import remove_ros_args
from .geometry import require_commissioning
from .profiles import load_settings
from .web import validate_server_uri


def terminate_group(process):
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGINT)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=8.)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=3.)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--fleet-config', required=True)
    parser.add_argument('--server-uri', default='')
    parser.add_argument('--retry-delay', type=float, default=5.)
    argv = sys.argv if args is None else [sys.argv[0], *args]
    options = parser.parse_args(remove_ros_args(argv)[1:])
    options.server_uri = validate_server_uri(options.server_uri)
    if not 1. <= options.retry_delay <= 60.:
        parser.error('retry-delay must be between 1 and 60 seconds')
    # Commissioning failure is a configuration error, never an automatic bypass.
    require_commissioning(load_settings(options.config))
    lock = Path(options.config).with_name('adapter_supervisor.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        print('Devi adapter supervisor already running', flush=True)
        return
    directory = Path(get_package_prefix('brin_devi_fleet_adapter'))/'lib/brin_devi_fleet_adapter'
    stop = False
    child = None

    def on_signal(_number, _frame):
        nonlocal stop
        stop = True

    previous = {number: signal.signal(number, on_signal) for number in (signal.SIGINT, signal.SIGTERM)}
    environment = {**os.environ, 'ROS_DOMAIN_ID': '0', 'RMW_IMPLEMENTATION': 'rmw_cyclonedds_cpp',
                   'BRIN_ENABLE_DISPATCH': '1'}
    try:
        while not stop:
            print('Devi: waiting for AMCL localization, Nav2 readiness, and laptop RMF core', flush=True)
            child = subprocess.Popen([str(directory/'preflight'), '--config', options.config,
                                      '--timeout', '12'], env=environment, start_new_session=True)
            preflight_deadline = time.monotonic() + 25.
            while child.poll() is None and not stop and time.monotonic() < preflight_deadline:
                time.sleep(0.1)
            if stop:
                break
            if child.poll() is None:
                terminate_group(child)
            if child.returncode == 0:
                print('Devi preflight accepted; starting one onboard fleet adapter', flush=True)
                command = ['ros2', 'launch', 'brin_devi_fleet_adapter', 'robot.launch.py',
                           'enable_dispatch:=true', 'integration_config:=' + options.config,
                           'fleet_config:=' + options.fleet_config]
                if options.server_uri:
                    command.append('server_uri:=' + options.server_uri)
                child = subprocess.Popen(command, env=environment, start_new_session=True)
                while child.poll() is None and not stop:
                    time.sleep(0.1)
            # Nav2 remains alive while the laptop is absent or localization is missing.
            deadline = time.monotonic() + options.retry_delay
            while not stop and time.monotonic() < deadline:
                time.sleep(0.1)
    finally:
        terminate_group(child)
        for number, handler in previous.items():
            signal.signal(number, handler)
        lock.close()
