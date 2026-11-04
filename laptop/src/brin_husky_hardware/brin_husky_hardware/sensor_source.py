"""Read real platform sensors through a separate RMW while retaining the bridge RMW."""
import base64
import json
import os
import subprocess
import sys

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from rclpy.serialization import deserialize_message, serialize_message
from sensor_msgs.msg import Imu
from nav_msgs.msg import Odometry
from tf2_msgs.msg import TFMessage


PREFIX = b'BRIN_SENSOR:'
TYPES = {'imu': Imu, 'odom': Odometry, 'static_tf': TFMessage}


class NativeSensorSource:
    def __init__(self, topics, rmw):
        if not topics or any(key not in TYPES or not topic.startswith('/')
                             for key, topic in topics.items()):
            raise ValueError('Native sensor sources must be known types and absolute topics')
        self.topics = topics
        env = os.environ.copy()
        env['RMW_IMPLEMENTATION'] = rmw
        if rmw != 'rmw_cyclonedds_cpp':
            env.pop('CYCLONEDDS_URI', None)
        self.process = subprocess.Popen(
            [sys.executable, '-u', '-m', 'brin_husky_hardware.sensor_source', json.dumps(topics)],
            stdout=subprocess.PIPE, env=env, bufsize=0)
        os.set_blocking(self.process.stdout.fileno(), False)
        self.pending = b''

    def poll(self):
        """Return the newest real sample per sensor without blocking the executor."""
        if self.process is None:
            return {}
        if self.process.poll() is not None:
            raise RuntimeError(f'Native sensor reader exited: {self.process.returncode}')
        latest = {}
        while True:
            try:
                block = os.read(self.process.stdout.fileno(), 65536)
            except BlockingIOError:
                break
            if not block:
                break
            self.pending += block
            while b'\n' in self.pending:
                line, self.pending = self.pending.split(b'\n', 1)
                if line.startswith(PREFIX):
                    label, payload = line[len(PREFIX):].split(b':', 1)
                    key = label.decode('ascii')
                    if key not in self.topics:
                        raise ValueError(f'Unexpected native sensor type: {key}')
                    message = deserialize_message(
                        base64.b64decode(payload, validate=True), TYPES[key])
                    if key == 'static_tf':
                        # Multiple latched writers publish different subtrees.
                        latest.setdefault(key, []).append(message)
                    else:
                        latest[key] = message
            if len(self.pending) > 1024 * 1024:
                raise ValueError('Native sensor reader frame exceeds limit')
        return latest

    def close(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.process.stdout.close()
        self.process = None


def main():
    topics = json.loads(sys.argv[1])
    if not topics or any(key not in TYPES or not topic.startswith('/')
                         for key, topic in topics.items()):
        raise ValueError('Invalid native sensor sources')
    rclpy.init(args=[])
    node = Node('brin_native_sensor_reader')

    def receive(message, key):
        # CDR preserves the original sensor fields, covariance and timestamp.
        sys.stdout.buffer.write(PREFIX + key.encode('ascii') + b':'
                                + base64.b64encode(serialize_message(message)) + b'\n')
        sys.stdout.buffer.flush()

    static_qos = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE,
                           durability=DurabilityPolicy.TRANSIENT_LOCAL)
    subscriptions = [node.create_subscription(
        TYPES[key], topic, lambda msg, key=key: receive(msg, key),
        static_qos if key == 'static_tf' else qos_profile_sensor_data)
        for key, topic in topics.items()]
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        for subscription in subscriptions:
            node.destroy_subscription(subscription)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
