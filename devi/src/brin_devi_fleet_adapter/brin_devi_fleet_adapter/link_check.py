"""Verify native RMF, private IPC, and real Nav2 services without a fleet."""
from datetime import timedelta
import json
import os
from pathlib import Path
import time

import rmf_adapter as rmf
from ament_index_python.packages import get_package_share_directory
from .domains import RmfObserver
from .gateway import Nav2Gateway
from .profiles import load_settings


def main():
    if os.environ.get('ROS_DOMAIN_ID') != '0':
        raise ValueError('Run through tools/devi.bash link-check with native domain 0')
    share = Path(get_package_share_directory('brin_devi_fleet_adapter'))
    gateway = Nav2Gateway(load_settings(share/'config/devi.yaml'))
    observer = RmfObserver()
    adapter = None
    try:
        rmf.init_rclcpp()
        adapter = rmf.Adapter.make('devi_rmf_link_check', wait_time=timedelta(seconds=12))
        deadline = time.monotonic() + 5.
        while time.monotonic() < deadline:
            observer.executor.spin_once(timeout_sec=0.05)
            gateway.poll()
        # A nonexistent UUID checks action service request/response transport.
        # No goal or cancellation is sent to Nav2.
        future = gateway.request('query_result')
        deadline = time.monotonic() + 4.
        while not future.done() and time.monotonic() < deadline:
            observer.executor.spin_once(timeout_sec=0.05)
            gateway.poll()
        responded = bool(future.done() and future.result() is not None
                         and future.result().status == 0)
        result = {
            'native_adapter_connected_to_schedule': adapter is not None,
            'nav2_action_available': gateway.fresh and gateway.state.get('nav2_action_available', False),
            'nav2_action_service_responded_to_unknown_goal': responded,
            'nav2_context_domain': gateway.state.get('robot_domain_id'),
            'rmf_observer_context_domain': observer.context.get_domain_id(),
            'nav2_rmw': 'rmw_fastrtps_cpp',
            'rmf_rmw': os.environ.get('RMW_IMPLEMENTATION'),
            'robot_registered': False, 'goals_sent': 0}
        print(json.dumps(result, indent=2), flush=True)
        return 0 if adapter is not None and result['nav2_action_available'] and responded else 2
    finally:
        del adapter
        gateway.close()
        observer.close()
