from pathlib import Path
import xml.etree.ElementTree as ET
import yaml
from brin_husky_bringup.prepare import prepare_robot

def test_fast_sensor_profile_preserves_hardware_and_fidelity(tmp_path):
    source = Path(__file__).resolve().parents[1]/'config/robots/husky_0/robot.yaml'
    original = source.read_bytes()
    fast = prepare_robot(source, tmp_path/'fast', 'fast')
    fidelity = prepare_robot(source, tmp_path/'fidelity', 'fidelity')
    assert source.read_bytes() == original
    for target, expected in ((fast, ('512', '1', '10')), (fidelity, ('1024', '64', '50'))):
        sensor = ET.parse(target/'robot.sim.urdf').find(".//sensor[@type='gpu_lidar']")
        assert tuple(sensor.find(k).text for k in ('lidar/scan/horizontal/samples',
            'lidar/scan/vertical/samples', 'update_rate')) == expected
        assert sensor.find('ignition_frame_id').text == 'husky_0/lidar3d_0_sensor_link'
        assert float(sensor.find('lidar/scan/horizontal/min_angle').text) < -3.14
        assert float(sensor.find('lidar/scan/horizontal/max_angle').text) > 3.14
    bridges = [b for p in (fast/'sensors/config').glob('*.yaml') for b in yaml.safe_load(p.read_text())]
    assert {b['ros_topic_name'] for b in bridges} == {'imu_0/data', 'lidar3d_0/scan'}
    assert all(b['direction'] == 'GZ_TO_ROS' and b['lazy'] and b['publisher_queue'] == 1 for b in bridges)
