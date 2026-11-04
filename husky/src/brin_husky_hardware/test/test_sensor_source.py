import base64
import os
from types import SimpleNamespace

import pytest
from rclpy.serialization import serialize_message
from sensor_msgs.msg import Imu
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
from tf2_msgs.msg import TFMessage

from brin_husky_hardware import sensor_source
from brin_husky_hardware.bridge import PhysicalTfBridge


def sample(stamp=42):
    message = Imu()
    message.header.stamp.sec = stamp
    message.header.stamp.nanosec = 123456789
    message.header.frame_id = 'imu_0_link'
    message.orientation.w = 0.99
    message.angular_velocity.z = 0.12
    message.linear_acceleration.x = 0.24
    message.orientation_covariance[0] = 0.03
    return message


def wire(message, kind='imu'):
    return (sensor_source.PREFIX + kind.encode() + b':'
            + base64.b64encode(serialize_message(message)) + b'\n')


@pytest.fixture
def reader(monkeypatch):
    read_fd, write_fd = os.pipe()
    stream = os.fdopen(read_fd, 'rb', buffering=0)
    events, creation = [], {}
    process = SimpleNamespace(stdout=stream, returncode=None)
    process.poll = lambda: process.returncode

    def terminate():
        events.append('terminate')
        process.returncode = 0

    process.terminate = terminate
    process.wait = lambda **kwargs: events.append('wait')

    def spawn(args, **kwargs):
        creation.update(args=args, **kwargs)
        return process

    monkeypatch.setenv('RMW_IMPLEMENTATION', 'rmw_cyclonedds_cpp')
    monkeypatch.setenv('CYCLONEDDS_URI', 'file:///existing.xml')
    monkeypatch.setattr(sensor_source.subprocess, 'Popen', spawn)
    source = sensor_source.NativeSensorSource(
        {'imu': '/physical/imu', 'odom': '/physical/odom',
         'static_tf': '/physical/tf_static'}, 'rmw_fastrtps_cpp')
    yield source, write_fd, process, events, creation
    source.close()
    os.close(write_fd)


def test_native_imu_preserves_real_sensor_sample_across_partial_pipe_reads(reader):
    source, fd, _, _, creation = reader
    message = sample()
    payload = wire(message)
    os.write(fd, payload[:30])
    assert source.poll() == {}
    os.write(fd, payload[30:])
    received = source.poll()['imu']
    assert serialize_message(received) == serialize_message(message)
    assert source.poll() == {}  # Never replay an old sample as new input.
    assert creation['env']['RMW_IMPLEMENTATION'] == 'rmw_fastrtps_cpp'
    assert 'CYCLONEDDS_URI' not in creation['env']
    assert os.environ['RMW_IMPLEMENTATION'] == 'rmw_cyclonedds_cpp'
    assert os.environ['CYCLONEDDS_URI'] == 'file:///existing.xml'


def test_native_reader_keeps_latest_sample_per_type_and_closes_child(reader):
    source, fd, _, events, _ = reader
    odom = Odometry()
    odom.header.stamp.sec = 39
    odom.header.frame_id = 'odom'
    odom.child_frame_id = 'base_link'
    odom.twist.twist.linear.x = 0.15
    os.write(fd, b'ROS log output\n' + wire(sample(40))
             + wire(odom, 'odom') + wire(sample(41)))
    samples = source.poll()
    assert samples['imu'].header.stamp.sec == 41
    assert serialize_message(samples['odom']) == serialize_message(odom)
    source.close()
    source.close()
    assert events == ['terminate', 'wait']


def test_dead_native_reader_does_not_supply_a_sample(reader):
    source, _, process, _, _ = reader
    process.returncode = 1
    with pytest.raises(RuntimeError, match='exited: 1'):
        source.poll()


def test_native_static_reader_preserves_all_latched_writer_batches(reader):
    source, fd, _, _, _ = reader
    for child in ('imu_0_link', 'laser_frame'):
        transform = TransformStamped()
        transform.header.frame_id = 'base_link'
        transform.child_frame_id = child
        transform.transform.rotation.w = 1.0
        os.write(fd, wire(TFMessage(transforms=[transform]), 'static_tf'))
    messages = source.poll()['static_tf']
    assert [message.transforms[0].child_frame_id for message in messages] == [
        'imu_0_link', 'laser_frame']
    assert source.poll() == {}


def test_bridge_keeps_original_imu_timestamp_and_fails_closed_on_reader_error():
    published, events = [], []
    message = sample()
    odom = Odometry()
    odom.header.stamp = message.header.stamp
    odom.header.frame_id = 'odom'
    odom.child_frame_id = 'base_link'
    bridge = SimpleNamespace(
        native_sensors=SimpleNamespace(
            poll=lambda: {'imu': message, 'odom': odom}, close=lambda: events.append('close')),
        robot_name='husky_0', map_frame='map',
        imu_pub=SimpleNamespace(publish=published.append),
        odom_pub=SimpleNamespace(publish=published.append),
        sensor_timer=SimpleNamespace(cancel=lambda: events.append('cancel')),
        get_logger=lambda: SimpleNamespace(error=lambda text: events.append('error')))
    bridge.on_imu = lambda msg: PhysicalTfBridge.on_imu(bridge, msg)
    bridge.on_odom = lambda msg: PhysicalTfBridge.on_odom(bridge, msg)
    PhysicalTfBridge.poll_native_sensors(bridge)
    assert published[0].header.frame_id == 'husky_0/imu_0_link'
    assert published[0].header.stamp == message.header.stamp
    assert published[0].angular_velocity == message.angular_velocity
    assert message.header.frame_id == 'imu_0_link'
    assert published[1].header.frame_id == 'husky_0/odom'
    assert published[1].child_frame_id == 'husky_0/base_link'
    assert published[1].header.stamp == odom.header.stamp

    def failed():
        raise RuntimeError('reader stopped')

    bridge.native_sensors.poll = failed
    PhysicalTfBridge.poll_native_sensors(bridge)
    assert len(published) == 2
    assert events == ['error', 'cancel', 'close']
