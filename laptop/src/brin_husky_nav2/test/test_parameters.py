from pathlib import Path
import yaml
from brin_husky_nav2.parameters import robot_parameters


def test_seven_stacks_have_disjoint_frames_and_observations():
    template = Path(__file__).resolve().parents[1]/'config/nav2.yaml'
    names = [f'husky_{i}' for i in range(7)]
    for name in names:
        root = robot_parameters(template, name)
        text = yaml.safe_dump(root)
        assert all(other not in text for other in names if other != name)
        assert '__ROBOT__' not in text
        parameters = root[name]
        amcl = parameters['amcl']['ros__parameters']
        assert amcl['base_frame_id'] == name+'/base_link'
        assert amcl['odom_frame_id'] == name+'/odom'
        assert amcl['global_frame_id'] == 'map'
        controller = parameters['controller_server']['ros__parameters']['FollowPath']
        assert controller['plugin'] == (
            'nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController'
        )
        assert controller['desired_linear_vel'] == 0.4
        assert controller['lookahead_dist'] == 0.6
        assert controller['use_collision_detection'] is True
        assert controller['allow_reversing'] is False
        for kind in ('local', 'global'):
            costmap = parameters[kind+'_costmap'][kind+'_costmap']['ros__parameters']
            assert costmap['obstacle_layer']['scan']['topic'].startswith('/'+name+'/')
            assert costmap['robot_base_frame'] == name+'/base_link'
            assert costmap['static_layer']['map_topic'] == '/map'
