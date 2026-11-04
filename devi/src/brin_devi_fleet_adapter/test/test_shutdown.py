"""Real localhost-only gateway shutdown, without goals or hardware access."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def test_process_group_sigint_allows_parent_to_close_ros_child(tmp_path):
    package = Path(__file__).resolve().parents[1]
    program = '''
import sys,time,yaml
from pathlib import Path
from brin_devi_fleet_adapter.gateway import Nav2Gateway
if __name__ == '__main__':
    settings=yaml.safe_load(open(sys.argv[1]))
    gateway=Nav2Gateway(settings)
    try:
        deadline=time.monotonic()+15.
        while time.monotonic()<deadline and not gateway.fresh:
            gateway.poll()
            time.sleep(.05)
        if not gateway.fresh:
            raise RuntimeError('Local diagnostic child did not become ready')
        Path(sys.argv[2]).write_text('ready')
        print('READY',flush=True)
        while True:
            time.sleep(.1)
    except KeyboardInterrupt:
        pass
    finally:
        gateway.close()
    assert gateway.process.exitcode == 0, gateway.process.exitcode
    print('CLEAN',flush=True)
'''
    environment = {**os.environ, 'ROS_LOCALHOST_ONLY': '1',
                   'ROS_LOG_DIR': str(tmp_path/'ros')}
    ready = tmp_path/'ready'
    process = subprocess.Popen([sys.executable, '-c', program, str(package/'config/devi.yaml'), str(ready)],
        env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True)
    try:
        deadline = time.monotonic() + 25.
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.05)
        assert ready.exists(), 'Gateway startup failed or timed out'
        # This is how systemd/launch deliver SIGINT to parent and child together.
        os.killpg(process.pid, signal.SIGINT)
        output, errors = process.communicate(timeout=12.)
        assert process.returncode == 0, output + errors
        assert 'CLEAN' in output
        assert 'Traceback' not in errors
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5.)
