#!/usr/bin/env bash
# Local build/run for komputer-utama; no SSH, sudo, robot startup or OS edits.
set -eo pipefail

usage() {
  printf '%s\n' \
    'Usage: bash tools/main.bash build|profile|waypoint|core|view|status|task|web [arguments]' \
    'core: one real-time RMF core; default profile gedungWS_0, no RViz window.' \
    'status: observe core, profile, building map and fleet states; no tasks.' \
    'profile/waypoint: require exactly one traffic_profile:=NAME argument.' \
    'view: RViz only; uses observation publishers from the main core.' \
    'web: optional existing RMF Web launcher; needs a separately installed runtime.' \
    'Optional: BRIN_RMF_UNDERLAY, BRIN_RMF_RMW, BRIN_RMF_CYCLONEDDS_URI.'
}
operation=${1:---help}
[[ $# == 0 ]] || shift
case "$operation" in
  --help) usage; exit 0 ;;
  build|core|profile|waypoint|view|status|task|web) ;;
  *) usage >&2; exit 2 ;;
esac
case "$operation" in
  build|status) [[ $# == 0 ]] || { usage >&2; exit 2; } ;;
  profile|waypoint)
    [[ $# == 1 && $1 == traffic_profile:=* && -n ${1#traffic_profile:=} ]] || {
      usage >&2; exit 2;
    }
    selected_profile=${1#traffic_profile:=} ;;
esac
for argument in "$@"; do
  case "$argument" in
    enable_dispatch:=*|start_nav2:=*|start_hokuyo:=*|use_sim_time:=*)
      printf 'Robot/simulation option cannot be forwarded by the main core launcher: %s\n' "$argument" >&2
      exit 2 ;;
  esac
done

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
workspace="$repo_dir/main"
source /opt/ros/humble/setup.bash
if [[ -n ${BRIN_RMF_UNDERLAY:-} ]]; then
  source "$BRIN_RMF_UNDERLAY"
fi
[[ $ROS_DISTRO == humble ]] || { printf '%s\n' 'ROS 2 Humble is required.' >&2; exit 2; }
if [[ $operation != build ]]; then
  [[ -f $workspace/install/local_setup.bash ]] || {
    printf '%s\n' 'Build this computer first: bash tools/main.bash build' >&2
    exit 2
  }
  for variable in AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH PYTHONPATH LD_LIBRARY_PATH PATH PKG_CONFIG_PATH; do
    IFS=: read -r -a entries <<< "${!variable-}"
    retained=''
    for entry in "${entries[@]}"; do
      case "$entry" in "$workspace/install"|"$workspace/install/"*|"$workspace/build/"*) continue ;; esac
      [[ -z $entry ]] || retained+="${retained:+:}$entry"
    done
    printf -v "$variable" '%s' "$retained"
    export "$variable"
  done
  source "$workspace/install/local_setup.bash"
  integration_prefix=$(ros2 pkg prefix brin_husky_distributed)
  [[ $integration_prefix == "$workspace/install/"* ]] || {
    printf 'Wrong main integration overlay: %s\n' "$integration_prefix" >&2
    exit 2
  }
fi

export ROS_DOMAIN_ID=0 ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION="${BRIN_RMF_RMW:-rmw_cyclonedds_cpp}"
[[ -z ${ROS_DISCOVERY_SERVER:-} ]] || {
  printf '%s\n' 'Review ROS_DISCOVERY_SERVER in this terminal before using the audited LAN path.' >&2
  exit 2
}
if [[ $RMW_IMPLEMENTATION == rmw_cyclonedds_cpp ]]; then
  export CYCLONEDDS_URI="${BRIN_RMF_CYCLONEDDS_URI:-file://$workspace/config/cyclonedds_lan.xml}"
fi
export COLCON_HOME="$workspace/.colcon" ROS_LOG_DIR="$workspace/log/ros"
mkdir -p "$ROS_LOG_DIR"
python3 -c 'import rmf_adapter, rmf_fleet_msgs, rmf_task_msgs' || {
  printf '%s\n' 'Install main/install-dependencies.bash prerequisites first.' >&2
  exit 2
}
case "$operation" in
  build)
    exec 8>"$workspace/log/build.lock"
    flock -n 8 || { printf '%s\n' 'Main workspace build is already running.' >&2; exit 2; }
    export COLCON_EXTENSION_BLOCKLIST="${COLCON_EXTENSION_BLOCKLIST:+$COLCON_EXTENSION_BLOCKLIST:}colcon_core.shell.ros_domain_id"
    cd "$workspace"
    exec colcon --log-base log build \
      --base-paths src "$repo_dir/laptop/src/brin_husky_distributed" \
      "$repo_dir/laptop/src/brin_husky_hardware" "$repo_dir/laptop/src/brin_husky_fleet_adapter" \
      --build-base build --install-base install --symlink-install \
      --packages-select brin_rmf_maps brin_husky_distributed brin_husky_hardware brin_husky_fleet_adapter ;;
  profile|waypoint)
    arguments=(--traffic-profile "$selected_profile")
    [[ $operation != waypoint ]] || arguments+=(--choose-waypoint)
    exec "$integration_prefix/lib/brin_husky_distributed/profile_info" "${arguments[@]}" ;;
  core)
    exec 8>"$workspace/log/core.lock"
    flock -n 8 || { printf '%s\n' 'Main RMF core is already running.' >&2; exit 2; }
    python3 "$repo_dir/tools/main_core_check.py" --require-absent
    cd "$workspace/log"
    exec ros2 launch "$workspace/launch/core.launch.py" "$@" ;;
  status) exec python3 "$repo_dir/tools/main_core_check.py" --status ;;
  view)
    exec ros2 launch brin_husky_distributed visualization.launch.py \
      start_visualizers:=false start_tf:=false "$@" ;;
  task) exec "$integration_prefix/lib/brin_husky_distributed/task_client" "$@" ;;
  web) exec ros2 launch brin_husky_distributed web.launch.py "$@" ;;
esac
