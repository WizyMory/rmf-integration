from geometry_msgs.msg import TransformStamped, PoseStamped
from nav_msgs.msg import Odometry, OccupancyGrid, Path
from sensor_msgs.msg import LaserScan
from tf2_msgs.msg import TFMessage

from brin_devi_fleet_adapter.visualization_bridge import (
    display_frame, display_message, LatestTelemetry, STREAMS)


def test_frames_are_unique_while_shared_map_and_data_are_preserved():
    assert [display_frame(frame) for frame in ('map', '/map', 'odom', 'base_link', 'devi/rplidar_link', '')] == [
        'map', 'map', 'devi/odom', 'devi/base_link', 'devi/rplidar_link', '']
    scan = LaserScan()
    scan.header.frame_id = 'rplidar_link'
    scan.header.stamp.sec = 123
    scan.ranges = [1., 2., 3.]
    output = display_message(scan)
    assert output.header.frame_id == 'devi/rplidar_link'
    assert output.header.stamp == scan.header.stamp
    assert output.ranges == scan.ranges
    assert scan.header.frame_id == 'rplidar_link'
    odom = Odometry()
    odom.header.frame_id, odom.child_frame_id = 'odom', 'base_link'
    odom.pose.pose.position.x = 2.1
    output = display_message(odom)
    assert output.header.frame_id == 'devi/odom'
    assert output.child_frame_id == 'devi/base_link'
    assert output.pose == odom.pose


def test_nested_path_and_tf_labels_are_rewritten_without_new_transforms():
    path = Path()
    path.header.frame_id = 'map'
    pose = PoseStamped()
    pose.header.frame_id = 'odom'
    pose.pose.position.y = -3.2
    path.poses = [pose]
    output = display_message(path)
    assert output.header.frame_id == 'map'
    assert output.poses[0].header.frame_id == 'devi/odom'
    assert output.poses[0].pose == pose.pose
    transform = TransformStamped()
    transform.header.frame_id, transform.child_frame_id = 'map', 'odom'
    transform.transform.translation.x = 19.4
    transform.transform.rotation.w = 1.
    output = display_message(TFMessage(transforms=[transform])).transforms[0]
    assert output.header.frame_id == 'map'
    assert output.child_frame_id == 'devi/odom'
    assert output.transform == transform.transform


def test_full_costmap_origin_and_cells_are_not_reprojected():
    message = OccupancyGrid()
    message.header.frame_id = 'odom'
    message.info.origin.position.x = -2.
    message.info.origin.position.y = -33.65
    message.data = [-1, 0, 100]
    result = display_message(message)
    assert result.header.frame_id == 'devi/odom'
    assert result.info == message.info
    assert result.data == message.data


def test_latest_cache_is_bounded_and_retains_all_static_publishers():
    cache = LatestTelemetry()
    for child in ('rplidar_link', 'wheel_left_link'):
        transform = TransformStamped()
        transform.header.frame_id, transform.child_frame_id = 'base_link', child
        cache.receive('tf_static', TFMessage(transforms=[transform]))
    for value in range(100):
        message = LaserScan()
        message.ranges = [float(value)]
        cache.receive('scan', message)
    batch = cache.take()
    assert set(batch) == {'scan', 'tf_static'}
    assert list(batch['scan'].ranges) == [99.]
    assert {item.child_frame_id for item in batch['tf_static'].transforms} == {'rplidar_link', 'wheel_left_link'}
    assert cache.take() == {}


def test_visualization_has_no_motion_or_control_outputs():
    assert set(STREAMS) == {'scan', 'scan_raw', 'global_costmap', 'local_costmap',
        'global_footprint', 'local_footprint', 'amcl', 'particles', 'odom',
        'plan', 'local_plan', 'smoothed_plan', 'received_plan', 'description', 'tf', 'tf_static'}
    for kind, source, suffix, durable in STREAMS.values():
        assert all(word not in source for word in ('cmd_vel', 'goal_pose', 'initialpose', 'set_pose'))
        assert not suffix.startswith('/')
