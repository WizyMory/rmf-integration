"""Generate reviewable files; never modify a Nav2 file or install a service."""
from pathlib import Path
import yaml


def transit_xml(config):
    nav = config['nav2']
    return f'''<root main_tree_to_execute="MainTree">
  <BehaviorTree ID="MainTree">
    <ReactiveFallback name="TransitArrivalOrNavigate">
      <GoalReached goal="{{goal}}" global_frame="{nav['map_frame']}" robot_base_frame="{nav['base_frame']}"/>
      <PipelineSequence name="TransitNavigation">
        <RateController hz="1.0">
          <ComputePathToPose goal="{{goal}}" path="{{path}}" planner_id="{nav['planner_id']}"/>
        </RateController>
        <FollowPath path="{{path}}" controller_id="{nav['controller_id']}"/>
      </PipelineSequence>
    </ReactiveFallback>
  </BehaviorTree>
</root>
'''


def nav2_fragment(config):
    nav = config['nav2']
    tolerance = nav['transit_xy_tolerance']
    if type(tolerance) not in (int, float) or tolerance <= 0:
        raise ValueError('Fill nav2.transit_xy_tolerance from the actual goal checker first')
    return yaml.safe_dump({name: {'ros__parameters': {'goal_reached_tol': float(tolerance)}}
                           for name in (nav['bt_navigator_node'],
                           nav['bt_navigator_node']+'_navigate_to_pose_rclcpp_node')}, sort_keys=False)


def systemd_quote(value):
    value = str(value)
    if any(c in value for c in '\n\r\x00'):
        raise ValueError('Invalid newline in service path')
    return '"'+value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')+'"'


def service(config, workspace, underlay=''):
    workspace = Path(workspace).resolve()
    if not (workspace/'tools/robot.bash').is_file():
        raise ValueError('workspace must be the modular/ root, containing tools/robot.bash')
    env = ('Environment='+systemd_quote('RMF_NAV2_UNDERLAY='+str(Path(underlay).resolve()))+'\n') if underlay else ''
    return f'''[Unit]
Description=Open-RMF Nav2 onboard adapter {config['robot']['name']}
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=120
StartLimitBurst=3

[Service]
Type=simple
WorkingDirectory={systemd_quote(workspace)}
{env}Environment=PYTHONUNBUFFERED=1
ExecStart=/bin/bash {systemd_quote(workspace/'tools/robot.bash')} run --config {systemd_quote(config['_path'])} --enable-dispatch
Restart=on-failure
RestartSec=15
KillSignal=SIGINT
KillMode=mixed
TimeoutStopSec=15

[Install]
WantedBy=default.target
'''
