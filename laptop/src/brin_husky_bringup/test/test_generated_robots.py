from pathlib import Path
import xml.etree.ElementTree as ET
import yaml
from brin_husky_bringup.prepare import prepare_robot, combine_controller_parameters


def test_generated_setups_preserve_reference_and_have_unique_tf(tmp_path):
    configs = Path(__file__).resolve().parents[1]/'config/robots'
    for name in tuple(f'husky_{i}' for i in range(7)):
        source = configs/name/'robot.yaml'
        original = source.read_bytes()
        target = prepare_robot(source, tmp_path/name)
        assert source.read_bytes() == original
        drive = yaml.safe_load((target/'platform/config/control.yaml').read_text())[name]['platform_velocity_controller']['ros__parameters']
        assert drive['base_frame_id'] == name+'/base_link'
        assert drive['odom_frame_id'] == name+'/odom'
        assert drive['enable_odom_tf'] is False
        ekf = yaml.safe_load((target/'platform/config/localization.yaml').read_text())[name]['ekf_node']['ros__parameters']
        assert ekf['world_frame'] == name+'/odom'
        assert ekf['base_link_frame'] == name+'/base_link'
        robot = ET.parse(target/'robot.sim.urdf').getroot()
        frames = [element.text for element in robot.findall('.//ignition_frame_id')]
        assert frames and all(frame.startswith(name+'/') for frame in frames)
        assert not any('PosePublisher' in p.get('name', '') for p in robot.findall('.//plugin'))
        assert all(':=tf' not in (r.text or '') for r in robot.findall('.//remapping'))
        assert robot.find('.//sensor/lidar/range/min').text == '0.15'
        assert '~/cmd_vel_unstamped:=cmd_vel' in [e.text for e in robot.findall('.//remapping')]
    combine_controller_parameters([tmp_path/name for name in tuple(f'husky_{i}' for i in range(7))])
    assert set(yaml.safe_load((tmp_path/'controllers.yaml').read_text())) == {f'husky_{i}' for i in range(7)}
    for name in tuple(f'husky_{i}' for i in range(7)):
        tree = ET.parse(tmp_path/name/'robot.sim.urdf')
        assert str(tmp_path/'controllers.yaml') in [p.text for p in tree.findall('.//plugin/parameters')]
