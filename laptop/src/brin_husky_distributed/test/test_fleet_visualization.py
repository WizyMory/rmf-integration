from pathlib import Path
from types import SimpleNamespace

from geometry_msgs.msg import TransformStamped
from tf2_msgs.msg import TFMessage
import yaml

from brin_husky_distributed.visualization_tf import VisualizationTF


def test_late_rviz_receives_complete_static_tree_for_both_robots():
    published = []
    node = SimpleNamespace(static={}, static_publisher=SimpleNamespace(publish=published.append))
    for parent, child in [('base_link','laser_frame'), ('devi/base_link','devi/rplidar_link')]:
        transform = TransformStamped()
        transform.header.frame_id, transform.child_frame_id = parent, child
        VisualizationTF.on_static(node, TFMessage(transforms=[transform]))
    assert {item.child_frame_id for item in published[-1].transforms} == {'laser_frame','devi/rplidar_link'}


def test_combined_preset_contains_real_devi_layers_and_preserves_husky():
    package = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((package/'rviz/devi_rmf.rviz').read_text())
    manager = config['Visualization Manager']
    displays = {item['Name']: item for item in manager['Displays']}
    assert displays['Devi sensors and Nav2']['Class'] == 'rviz_common/Group'
    assert displays['Husky sensors and Nav2']['Class'] == 'rviz_common/Group'
    devi = {item['Name']: item for item in displays['Devi sensors and Nav2']['Displays']}
    assert devi['Devi robot model']['TF Prefix'] == 'devi'
    assert devi['Devi robot model']['Description Topic']['Value'] == '/devi/viz/robot_description'
    for name, suffix in [('Devi filtered laser','scan'),('Devi global costmap','global_costmap/costmap'),
                         ('Devi local costmap','local_costmap/costmap'),('Devi global plan','plan'),
                         ('Devi local plan','local_plan'),('Devi AMCL pose and covariance','amcl_pose'),
                         ('Devi AMCL particles','particle_cloud')]:
        assert devi[name]['Enabled']
        assert devi[name]['Topic']['Value'] == '/devi/viz/' + suffix
    for name in ('Devi global costmap','Devi local costmap'):
        assert devi[name]['Topic']['Durability Policy'] == 'Transient Local'
    assert devi['Devi filtered laser']['Topic']['Reliability Policy'] == 'Best Effort'
    assert displays['RMF fleet positions']['Topic']['Value'] == '/fleet_markers'
    assert displays['Husky sensors and Nav2']['Enabled']
    assert manager['Global Options']['Fixed Frame'] == 'map'
