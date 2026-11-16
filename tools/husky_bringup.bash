#!/usr/bin/env bash
# Physical Husky boot entrypoint; preserve Clearpath services and the Nav2 underlay.
set -eo pipefail
operation=${1:-help}
case "$operation" in build|prepare|run|navigation-only) shift ;; *)
  printf '%s\n' 'Usage: bash tools/husky_bringup.bash build|prepare|run|navigation-only [supervisor arguments]'
  exit 2 ;;
esac
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
[[ $repo_dir == /home/husky/rmf-integration ]] || {
  printf '%s\n' 'Physical Husky bringup must run from /home/husky/rmf-integration.' >&2; exit 2;
}
source /opt/ros/humble/setup.bash
source /etc/clearpath/setup.bash
source /home/husky/ros2_ws/install/local_setup.bash
source /home/husky/rmf_ws/install/local_setup.bash
export ROS_DOMAIN_ID=0 ROS_LOCALHOST_ONLY=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
unset ROS_DISCOVERY_SERVER
export CYCLONEDDS_URI="file://$repo_dir/husky/src/brin_husky_distributed/config/cyclonedds_lan.xml"
export COLCON_HOME="$repo_dir/husky/.colcon" ROS_LOG_DIR="$repo_dir/husky/log/ros"
mkdir -p "$ROS_LOG_DIR"
if [[ $operation == build ]]; then
  export COLCON_EXTENSION_BLOCKLIST="${COLCON_EXTENSION_BLOCKLIST:+$COLCON_EXTENSION_BLOCKLIST:}colcon_core.shell.ros_domain_id"
  cd "$repo_dir/husky"
  exec colcon --log-base log build --base-paths src --build-base build --install-base install \
    --symlink-install --packages-select brin_husky_autostart
fi
# Restore overlay priority even if an interactive shell sourced the old workspace.
for variable in AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH PYTHONPATH LD_LIBRARY_PATH PATH; do
  IFS=: read -r -a entries <<< "${!variable-}"
  retained=''
  for entry in "${entries[@]}"; do
    case "$entry" in "$repo_dir/husky/install"|"$repo_dir/husky/install/"*|"$repo_dir/husky/build/"*) continue ;; esac
    [[ -n $entry ]] && retained+="${retained:+:}$entry"
  done
  printf -v "$variable" '%s' "$retained"
  export "$variable"
done
source "$repo_dir/husky/install/local_setup.bash"
prefix=$(ros2 pkg prefix brin_husky_autostart)
[[ $prefix == "$repo_dir/husky/install/"* ]] || { printf '%s\n' 'Wrong autostart overlay' >&2; exit 2; }
arguments=(--runtime-dir "$repo_dir/husky/log/bringup_runtime")
[[ $operation == prepare ]] && arguments+=(--prepare-only)
[[ $operation == navigation-only ]] && arguments+=(--navigation-only)
exec "$prefix/lib/brin_husky_autostart/bringup_supervisor" "${arguments[@]}" "$@"
