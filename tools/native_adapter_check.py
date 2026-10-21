#!/usr/bin/env python3
"""Verify a real RMF adapter can reach the laptop schedule; no robot or fleet.

Run on Husky while exactly one RMF schedule is running on the laptop.
This registers a diagnostic schedule query, NOT a robot, task or goal.
Also use an external timeout, e.g. timeout --signal=INT --kill-after=3s 25s.
"""
import argparse
from datetime import timedelta
import json
import os


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wait', type=float, default=12.0)
    args = parser.parse_args()
    if not 1.0 <= args.wait <= 60.0:
        parser.error('wait must be between 1 and 60 seconds')
    if os.environ.get('ROS_DOMAIN_ID', '0') != '0':
        parser.error('this physical integration uses ROS_DOMAIN_ID=0')

    import rmf_adapter as rmf
    import rmf_fleet_msgs  # noqa: F401: verify required runtime
    import rmf_task_msgs  # noqa: F401: verify required runtime

    rmf.init_rclcpp()
    adapter = rmf.Adapter.make(
        'husky_rmf_link_check', wait_time=timedelta(seconds=args.wait))
    connected = adapter is not None
    # Adapter.make already spins a temporary executor until the schedule
    # writer and mirror are ready (Humble Adapter::Implementation::make).
    # Do not launch a background executor just to stop it immediately: this
    # check has no fleet and a teardown crash was observed with that lifecycle
    # during a robot-side test. The underlying native cause is not established.
    # Release native objects while the extension is still alive, before
    # interpreter teardown. Production adapter lifecycle is unchanged.
    del adapter
    print(json.dumps({
        'native_adapter_connected_to_schedule': connected,
        'robot_registered': False, 'goals_sent': 0,
    }), flush=True)
    return 0 if connected else 2


if __name__ == '__main__':
    raise SystemExit(main())
