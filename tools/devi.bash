#!/usr/bin/env bash
# Build/run only. Does not change devi_ws, shell startup, services, or networking.
set -eo pipefail
usage() {
  printf '%s\n' 'Usage: bash tools/devi.bash build|bringup|visualization|supervisor|profile|inspect|link-check|preflight|adapter [launch arguments]' \
    'bringup: one onboard Nav2 stack on gedungWS_0, configured startup pose, automatic RMF readiness loop.' \
    'Other run modes use the already running Nav2 in domain 73; native RMF uses domain 0.' \
    'adapter requires BRIN_ENABLE_DISPATCH=1, commissioning, and passing preflight.'
}
operation=${1:---help}
[[ $# == 0 ]] || shift
case "$operation" in
  --help) usage; exit 0 ;;
  build|bringup|visualization|supervisor|profile|inspect|link-check|preflight) ;;
  adapter)
    if [[ ${BRIN_ENABLE_DISPATCH:-0} != 1 ]]; then
      printf '%s\n' 'Refusing dispatch. Complete Devi commissioning, then explicitly set BRIN_ENABLE_DISPATCH=1.' >&2
      exit 2
    fi ;;
  *) usage >&2; exit 2 ;;
esac
if [[ $operation == build || $operation == visualization || $operation == supervisor || $operation == profile || $operation == inspect || $operation == link-check ]]; then
  [[ $# == 0 ]] || { usage >&2; exit 2; }
fi
for argument in "$@"; do
  case "$argument" in
    enable_dispatch:=*|start_nav2:=*|use_sim_time:=*|robot_domain_id:=*|rmf_domain_id:=*)
      printf 'Option is controlled by this script: %s\n' "$argument" >&2; exit 2 ;;
  esac
done
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
workspace="$repo_dir/devi"
source /opt/ros/humble/setup.bash
source "${DEVI_UNDERLAY:-/home/devi/devi_ws/install/local_setup.bash}"
[[ $ROS_DISTRO == humble ]] || { printf '%s\n' 'ROS 2 Humble is required.' >&2; exit 2; }
# Native RMF and the domain-0 state observer. Python Nav2 explicitly uses context 73.
# Middleware applies to integration processes only, not the running Nav2.
export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION="${DEVI_RMF_RMW:-rmw_cyclonedds_cpp}"
export ROS_LOCALHOST_ONLY=0
if [[ $RMW_IMPLEMENTATION == rmw_cyclonedds_cpp ]]; then
  export CYCLONEDDS_URI="${DEVI_RMF_CYCLONEDDS_URI:-file://$workspace/src/brin_devi_fleet_adapter/config/cyclonedds_rmf.xml}"
fi
if [[ -n ${ROS_DISCOVERY_SERVER:-} ]]; then
  printf '%s\n' 'Review ROS_DISCOVERY_SERVER before starting this direct DDS integration.' >&2
  exit 2
fi
export COLCON_HOME="$workspace/.colcon" ROS_LOG_DIR="$workspace/log/ros"
mkdir -p -- "$ROS_LOG_DIR"
python3 -c 'import rmf_adapter, rmf_fleet_msgs, rmf_task_msgs; print("Devi RMF runtime imports OK")'
if [[ $operation == build ]]; then
  cd -- "$workspace"
  export COLCON_EXTENSION_BLOCKLIST="${COLCON_EXTENSION_BLOCKLIST:+$COLCON_EXTENSION_BLOCKLIST:}colcon_core.shell.ros_domain_id"
  exec colcon --log-base log build --base-paths src \
    --build-base build --install-base install --symlink-install \
    --packages-select brin_devi_fleet_adapter
fi
[[ -f $workspace/install/local_setup.bash ]] || { printf '%s\n' 'Build Devi integration first.' >&2; exit 2; }
# Restore precedence even when another overlay was sourced later in this shell.
for overlay_variable in AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH PYTHONPATH LD_LIBRARY_PATH PATH PKG_CONFIG_PATH; do
  IFS=: read -r -a overlay_entries <<< "${!overlay_variable-}"
  overlay_retained=''
  for overlay_entry in "${overlay_entries[@]}"; do
    case "$overlay_entry" in
      "$workspace/install"|"$workspace/install/"*|"$workspace/build/"*) continue ;;
    esac
    [[ -z $overlay_entry ]] && continue
    overlay_retained+="${overlay_retained:+:}$overlay_entry"
  done
  printf -v "$overlay_variable" '%s' "$overlay_retained"
  export "$overlay_variable"
done
source "$workspace/install/local_setup.bash"
integration_prefix=$(ros2 pkg prefix brin_devi_fleet_adapter)
[[ $integration_prefix == "$workspace/install/"* ]] || { printf 'Wrong Devi overlay: %s\n' "$integration_prefix" >&2; exit 2; }
selected_config="$workspace/src/brin_devi_fleet_adapter/config/devi.yaml"
selected_fleet="$workspace/src/brin_devi_fleet_adapter/config/fleet_config.yaml"
if [[ -f $workspace/log/bringup_runtime/integration.yaml && -f $workspace/log/bringup_runtime/fleet.yaml ]]; then
  selected_config="$workspace/log/bringup_runtime/integration.yaml"
  selected_fleet="$workspace/log/bringup_runtime/fleet.yaml"
fi
case "$operation" in
  bringup) exec ros2 launch brin_devi_fleet_adapter bringup.launch.py "$@" ;;
  visualization) exec ros2 run brin_devi_fleet_adapter visualization_bridge ;;
  supervisor) exec ros2 run brin_devi_fleet_adapter adapter_supervisor --config "$selected_config" --fleet-config "$selected_fleet" ;;
  profile) exec ros2 run brin_devi_fleet_adapter profile_info ;;
  link-check) exec ros2 run brin_devi_fleet_adapter link_check ;;
  inspect)
    exec "$integration_prefix/lib/brin_devi_fleet_adapter/preflight" \
      --config "$selected_config" --inspect ;;
  preflight|adapter)
    dispatch=false
    [[ $operation == adapter ]] && dispatch=true
    exec ros2 launch brin_devi_fleet_adapter robot.launch.py \
      enable_dispatch:="$dispatch" integration_config:="$selected_config" fleet_config:="$selected_fleet" "$@" ;;
esac
