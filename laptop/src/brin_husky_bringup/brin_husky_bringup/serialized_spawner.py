"""Serialize Humble plugin loading across controller managers in one Gazebo."""
import argparse
import fcntl
import os
from pathlib import Path
import signal
import subprocess
from ament_index_python.packages import get_package_prefix


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--lock-file', required=True)
    args, remaining = parser.parse_known_args()
    executable = Path(get_package_prefix('controller_manager'))/'lib/controller_manager/spawner'
    child = None

    def stop(signum, frame):
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signum)
        else:
            raise SystemExit(128+signum)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    with open(args.lock_file, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        child = subprocess.Popen([str(executable), *remaining], start_new_session=True)
        result = child.wait()
    raise SystemExit(result)
