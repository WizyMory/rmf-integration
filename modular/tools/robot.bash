#!/usr/bin/env bash
# All source/build paths are restricted to this independent modular workspace.
set -eo pipefail
module_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
operation=${1:---help}
if [[ $operation == build ]]; then
  [[ $# == 1 ]] || { printf '%s\n' 'build takes no arguments'; exit 2; }
  source /opt/ros/humble/setup.bash
  if [[ -n ${RMF_NAV2_UNDERLAY:-} ]]; then source "$RMF_NAV2_UNDERLAY"; fi
  export COLCON_HOME="$module_dir/.colcon"
  export COLCON_EXTENSION_BLOCKLIST="${COLCON_EXTENSION_BLOCKLIST:+$COLCON_EXTENSION_BLOCKLIST:}colcon_core.shell.ros_domain_id"
  cd "$module_dir"
  exec colcon --log-base log build --base-paths src --build-base build \
    --install-base install --packages-select rmf_nav2_onboard --symlink-install
fi
needs_ros=false
case "$operation" in
  inspect|preflight|run|publish-profile|core) needs_ros=true ;;
  task) for arg in "$@"; do [[ $arg != --send ]] || needs_ros=true; done ;;
esac
if [[ $needs_ros == true ]]; then
    source /opt/ros/humble/setup.bash
    if [[ -n ${RMF_NAV2_UNDERLAY:-} ]]; then source "$RMF_NAV2_UNDERLAY"; fi
    [[ -f $module_dir/install/local_setup.bash ]] || {
      printf '%s\n' 'Build this modular workspace on this device first.' >&2; exit 2;
    }
    source "$module_dir/install/local_setup.bash"
    [[ $ROS_DISTRO == humble ]] || { printf '%s\n' 'ROS 2 Humble is required'; exit 2; }
fi
# Source-first import keeps offline tools usable before colcon is installed.
export PYTHONPATH="$module_dir/src/rmf_nav2_onboard${PYTHONPATH:+:$PYTHONPATH}"
export RMF_NAV2_MODULE_ROOT="$module_dir"
export ROS_LOG_DIR="$module_dir/log/ros"
exec python3 -m rmf_nav2_onboard.cli "$@"
