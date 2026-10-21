#!/usr/bin/env bash
# Repository-local build/run only. No SSH, copying, sudo, network or service edits.
set -eo pipefail

usage() {
  printf '%s\n' \
    'Usage: bash tools/integration.bash laptop|husky build|profile|core|preflight|adapter|web [launch arguments]' \
    'build: builds only the four integration packages for the selected computer.' \
    'core/web: laptop only. preflight/adapter: Husky only; Nav2/sensors must already run.' \
    'adapter additionally requires BRIN_ENABLE_DISPATCH=1 and operator acceptance.' \
    'Optional: BRIN_RMF_UNDERLAY=/absolute/path/to/local_setup.bash' \
    'Default: Cyclone DDS with the target-specific repository Wi-Fi profile.' \
    'Optional: BRIN_RMF_RMW or BRIN_RMF_CYCLONEDDS_URI (integration processes only).'
}

if [[ ${1:-} == --help || $# -lt 2 ]]; then
  usage
  [[ ${1:-} == --help ]] && exit 0
  exit 2
fi
target=$1
operation=$2
shift 2
case "$target:$operation" in
  laptop:build|husky:build|laptop:profile|husky:profile|laptop:core|laptop:web|husky:preflight) ;;
  husky:adapter)
    if [[ ${BRIN_ENABLE_DISPATCH:-0} != 1 ]]; then
      printf '%s\n' 'Refusing dispatch. Complete physical acceptance first; then explicitly set BRIN_ENABLE_DISPATCH=1.' >&2
      exit 2
    fi ;;
  *) usage >&2; exit 2 ;;
esac
if [[ $operation == build || $operation == profile ]]; then
  [[ $# == 0 ]] || { printf '%s\n' 'This operation does not accept extra arguments.' >&2; exit 2; }
fi
for argument in "$@"; do
  case "$argument" in
    enable_dispatch:=*|start_nav2:=*|start_hokuyo:=*|use_sim_time:=*)
      printf '%s\n' "Safety option is controlled by this script, not forwarded: $argument" >&2
      exit 2 ;;
  esac
done

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
workspace="$repo_dir/$target"
source /opt/ros/humble/setup.bash
if [[ $target == laptop ]]; then
  source /mnt/UbuntuData/clearpath_ws/install/local_setup.bash
  source "${BRIN_RMF_UNDERLAY:-/mnt/UbuntuData/BRIN_ws/install/local_setup.bash}"
else
  source /etc/clearpath/setup.bash
  source /home/husky/ros2_ws/install/local_setup.bash
  if [[ -n ${BRIN_RMF_UNDERLAY:-} ]]; then
    source "$BRIN_RMF_UNDERLAY"
  fi
fi
[[ $ROS_DISTRO == humble ]] || { printf '%s\n' 'ROS 2 Humble is required.' >&2; exit 2; }
if [[ $operation != build ]]; then
  if [[ ! -f $workspace/install/local_setup.bash ]]; then
    printf '%s\n' "Build the $target integration workspace on this computer first." >&2
    exit 2
  fi
  source "$workspace/install/local_setup.bash"
  integration_prefix=$(ros2 pkg prefix brin_husky_distributed)
  if [[ $integration_prefix != "$workspace/install/"* ]]; then
    printf '%s\n' "Wrong integration overlay selected: $integration_prefix" >&2
    exit 2
  fi
fi

# Apply AFTER sourcing overlays; never change the environment of platform services.
export ROS_DOMAIN_ID=0 ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION="${BRIN_RMF_RMW:-rmw_cyclonedds_cpp}"
if [[ -n ${ROS_DISCOVERY_SERVER:-} ]]; then
  printf '%s\n' 'ROS_DISCOVERY_SERVER is set. Review it, or unset it in this terminal for the validated LAN discovery path.' >&2
  exit 2
fi
if [[ $RMW_IMPLEMENTATION == rmw_cyclonedds_cpp ]]; then
  # Do not inherit a simulation localhost profile. Only this child process
  # receives the repository profile; platform service environments are untouched.
  export CYCLONEDDS_URI="${BRIN_RMF_CYCLONEDDS_URI:-file://$workspace/src/brin_husky_distributed/config/cyclonedds_lan.xml}"
  printf 'Integration CYCLONEDDS_URI=%s\n' "$CYCLONEDDS_URI"
fi
export COLCON_HOME="$workspace/.colcon"
export ROS_LOG_DIR="$workspace/log/ros"
mkdir -p -- "$ROS_LOG_DIR"
printf 'Integration target=%s operation=%s domain=%s RMW=%s real_time=true\n' \
  "$target" "$operation" "$ROS_DOMAIN_ID" "$RMW_IMPLEMENTATION"
python3 -c 'import rmf_adapter, rmf_fleet_msgs, rmf_task_msgs; print("RMF runtime import OK")'

case "$operation" in
  build)
    export COLCON_EXTENSION_BLOCKLIST="${COLCON_EXTENSION_BLOCKLIST:+$COLCON_EXTENSION_BLOCKLIST:}colcon_core.shell.ros_domain_id"
    cd -- "$workspace"
    exec colcon --log-base log build --base-paths src \
      --build-base build --install-base install --symlink-install \
      --packages-select brin_rmf_maps brin_husky_fleet_adapter brin_husky_hardware brin_husky_distributed ;;
  profile) exec ros2 run brin_husky_distributed profile_info ;;
  core)
    cd -- "$workspace/log"
    exec ros2 launch brin_husky_distributed laptop.launch.py "$@" ;;
  web) exec ros2 launch brin_husky_distributed web.launch.py "$@" ;;
  preflight|adapter)
    dispatch=false
    [[ $operation == adapter ]] && dispatch=true
    exec ros2 launch brin_husky_distributed robot.launch.py \
      start_nav2:=false start_hokuyo:=false enable_dispatch:="$dispatch" "$@" ;;
esac
