#!/usr/bin/env bash
# Run one component on komputer-utama. No robot startup or OS configuration.
set -eo pipefail
operation=${1:---help}
case "$operation" in
  --help) printf '%s\n' 'Usage: bash main/bringup.bash api|dashboard|rviz|browser'; exit 0 ;;
  api|dashboard|rviz|browser) [[ $# == 1 ]] || exit 2 ;;
  *) exit 2 ;;
esac
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
set -a
source "$repo_dir/main/config/bringup.env"
set +a
cd "$repo_dir"
setup_ros() {
  source /opt/ros/humble/setup.bash
  source "$repo_dir/main/install/local_setup.bash"
  export ROS_DOMAIN_ID=0 ROS_LOCALHOST_ONLY=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
  export CYCLONEDDS_URI="file://$repo_dir/main/config/cyclonedds_lan.xml"
  export ROS_LOG_DIR="$repo_dir/main/log/ros"
}
case "$operation" in
  api)
    setup_ros
    export RMF_API_SERVER_CONFIG="$repo_dir/laptop/src/brin_husky_distributed/web/api_config.py"
    export RMF_SERVER_USE_SIM_TIME=false BRIN_WEB_RUNTIME="$repo_dir/main/log/rmf_web_real"
    export BRIN_WEB_API_HOST="$BRIN_MAIN_IP" BRIN_WEB_PUBLIC_URL="http://$BRIN_MAIN_IP:8000"
    python3 -c 'import os; from brin_husky_distributed.web_runtime import web_paths; web_paths(os.environ["RMF_WEB_ROOT"])'
    cd "$RMF_WEB_ROOT/packages/api-server"
    exec "$RMF_WEB_ROOT/.venv/bin/python" -m api_server ;;
  dashboard)
    setup_ros
    exec python3 "$repo_dir/main/web/dashboard_server.py" \
      --directory "$repo_dir/main/log/web/dashboard" --host "$BRIN_MAIN_IP" --port 3000 --battery-ros ;;
  rviz)
    [[ -n ${DISPLAY:-}${WAYLAND_DISPLAY:-} ]] || { printf '%s\n' 'No desktop display available.' >&2; exit 1; }
    setup_ros
    ready=false
    for attempt in 1 2 3 4 5 6; do
      if bash tools/main.bash status; then ready=true; break; fi
      sleep 2
    done
    [[ $ready == true ]] || exit 1
    package_prefix=$(ros2 pkg prefix brin_husky_distributed)
    [[ $package_prefix == "$repo_dir/main/install/"* ]] || exit 2
    rviz_prefix=$(ros2 pkg prefix rviz2)
    # Same observation remaps as visualization.launch.py. Executing RViz
    # directly lets systemd detect a crash rather than a successful ros2-launch exit.
    exec "$rviz_prefix/lib/rviz2/rviz2" \
      -d "$package_prefix/share/brin_husky_distributed/rviz/devi_rmf.rviz" \
      --ros-args -r __node:=husky_rmf_rviz -r __ns:=/a200_1060 -p use_sim_time:=false \
      -r /tf:=/rmf_visualization/tf -r /tf_static:=/rmf_visualization/tf_static \
      -r /initialpose:=/a200_1060/initialpose -r /goal_pose:=/a200_1060/goal_pose \
      -r /clicked_point:=/a200_1060/clicked_point ;;
  browser)
    [[ -n ${DISPLAY:-}${WAYLAND_DISPLAY:-} ]] || { printf '%s\n' 'No desktop display available.' >&2; exit 1; }
    python3 main/wait_ready.py http "http://$BRIN_MAIN_IP:8000/fleets"
    python3 main/wait_ready.py http "http://$BRIN_MAIN_IP:3000/"
    exec /usr/bin/google-chrome --guest --no-first-run --no-default-browser-check \
      --user-data-dir=/home/rslab/.local/share/brin-rmf-browser \
      --app="http://$BRIN_MAIN_IP:3000/" ;;
esac
