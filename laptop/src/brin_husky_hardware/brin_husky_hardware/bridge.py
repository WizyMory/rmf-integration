"""Mirror a physical robot's namespaced TF into the shared prefixed TF tree."""
from copy import deepcopy
from pathlib import Path

from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from rclpy.qos import (DurabilityPolicy, QoSProfile, ReliabilityPolicy,
                       qos_profile_sensor_data)
from sensor_msgs.msg import Imu, LaserScan
from std_msgs.msg import Bool
from tf2_msgs.msg import TFMessage
import yaml


def prefixed_frame(frame, robot_name, map_frame='map'):
    frame = frame.lstrip('/')
    if not frame:
        raise ValueError('TF frame is empty')
    if frame == map_frame or frame.startswith(robot_name + '/'):
        return frame
    return robot_name + '/' + frame


def rewrite_transforms(message, robot_name, map_frame='map'):
    result = TFMessage()
    for source in message.transforms:
        try:
            parent = prefixed_frame(source.header.frame_id, robot_name, map_frame)
            child = prefixed_frame(source.child_frame_id, robot_name, map_frame)
        except ValueError:
            continue
        if parent == child or child == map_frame:
            continue
        transform = deepcopy(source)
        transform.header.frame_id = parent
        transform.child_frame_id = child
        result.transforms.append(transform)
    return result


def valid_sources(config):
    topics = list(config['tf_topics']) + list(config['tf_static_topics'])
    if not topics or len(topics) != len(set(topics)):
        raise ValueError('TF source topics must be nonempty and distinct')
    if any(not topic.startswith('/') or topic in ('/tf', '/tf_static') for topic in topics):
        raise ValueError('TF sources must be absolute and cannot be shared output topics')
    return topics


class PhysicalTfBridge(Node):
    def __init__(self):
        super().__init__('brin_physical_tf_bridge')
        self.declare_parameter('config_file', '')
        config = yaml.safe_load(Path(self.get_parameter('config_file').value).read_text())
        valid_sources(config)
        self.robot_name = config['robot_name']
        self.map_frame = config.get('map_frame', 'map')
        dynamic_qos = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE)
        source_qos = QoSProfile(depth=100, reliability=ReliabilityPolicy.BEST_EFFORT)
        static_qos = QoSProfile(
            depth=1, reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.tf_pub = self.create_publisher(TFMessage, '/tf', dynamic_qos)
        self.static_pub = self.create_publisher(TFMessage, '/tf_static', static_qos)
        self.status_pub = self.create_publisher(
            Bool, f'/{self.robot_name}/hardware_tf_conflict', static_qos)
        self.status_pub.publish(Bool(data=False))
        self.source_by_child = {}
        self.conflict = False
        self.scan_pub = self.create_publisher(
            LaserScan, f'/{self.robot_name}/scan', qos_profile_sensor_data)
        self.odom_pub = self.create_publisher(
            Odometry, f'/{self.robot_name}/platform/odom/filtered',
            qos_profile_sensor_data)
        self.imu_pub = self.create_publisher(
            Imu, f'/{self.robot_name}/sensors/imu_0/data',
            qos_profile_sensor_data)
        self.static_by_child = {}
        self.subscriptions = []
        for topic in config['tf_topics']:
            self.subscriptions.append(self.create_subscription(
                TFMessage, topic,
                lambda message, source=topic: self.on_dynamic(message, source),
                source_qos))
        for topic in config['tf_static_topics']:
            self.subscriptions.append(self.create_subscription(
                TFMessage, topic,
                lambda message, source=topic: self.on_static(message, source),
                static_qos))
        self.subscriptions.append(self.create_subscription(
            LaserScan, config['scan_topic'], self.on_scan, qos_profile_sensor_data))
        self.subscriptions.append(self.create_subscription(
            Odometry, config['odom_topic'], self.on_odom, qos_profile_sensor_data))
        self.subscriptions.append(self.create_subscription(
            Imu, config['imu_topic'], self.on_imu, qos_profile_sensor_data))
        self.get_logger().info(
            f'{self.robot_name}: mirroring {len(self.subscriptions)} physical TF topics')

    def accepted_transforms(self, message, source):
        accepted = TFMessage()
        for transform in message.transforms:
            child = transform.child_frame_id
            authority = (transform.header.frame_id, source)
            previous = self.source_by_child.get(child)
            if previous is not None and previous != authority:
                if not self.conflict:
                    self.get_logger().error(
                        f'Conflicting TF authority for {child}: {previous} vs {authority}')
                self.conflict = True
                self.status_pub.publish(Bool(data=True))
                continue
            self.source_by_child[child] = authority
            accepted.transforms.append(transform)
        return accepted

    def on_dynamic(self, message, source=''):
        converted = rewrite_transforms(message, self.robot_name, self.map_frame)
        converted = self.accepted_transforms(converted, source)
        if converted.transforms:
            self.tf_pub.publish(converted)

    def on_static(self, message, source=''):
        converted = rewrite_transforms(message, self.robot_name, self.map_frame)
        converted = self.accepted_transforms(converted, source)
        for transform in converted.transforms:
            self.static_by_child[transform.child_frame_id] = transform
        if converted.transforms:
            self.static_pub.publish(TFMessage(transforms=list(self.static_by_child.values())))

    def on_scan(self, message):
        output = deepcopy(message)
        output.header.frame_id = prefixed_frame(
            message.header.frame_id, self.robot_name, self.map_frame)
        self.scan_pub.publish(output)

    def on_odom(self, message):
        output = deepcopy(message)
        output.header.frame_id = prefixed_frame(
            message.header.frame_id, self.robot_name, self.map_frame)
        output.child_frame_id = prefixed_frame(
            message.child_frame_id, self.robot_name, self.map_frame)
        self.odom_pub.publish(output)

    def on_imu(self, message):
        output = deepcopy(message)
        output.header.frame_id = prefixed_frame(
            message.header.frame_id, self.robot_name, self.map_frame)
        self.imu_pub.publish(output)


def main(args=None):
    rclpy.init(args=args)
    node = PhysicalTfBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
