#!/usr/bin/env bash
# Run on komputer-utama. Installs only the Humble core/build prerequisites.
set -euo pipefail

mode=${1:---check}
case "$mode" in
  --check|--install) ;;
  *) printf '%s\n' 'Usage: bash main/install-dependencies.bash [--check|--install]' >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || exit 2
source /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 22.04 && -f /opt/ros/humble/setup.bash ]] || {
  printf '%s\n' 'Requires Ubuntu 22.04 with ROS 2 Humble already installed.' >&2
  exit 2
}
packages=(
  git python3-colcon-common-extensions python3-pip python3-venv
  python3-pil python3-numpy python3-yaml python3-pytest
  ros-humble-rmf-fleet-adapter-python ros-humble-rmf-task-ros2
  ros-humble-rmf-traffic-ros2 ros-humble-rmf-building-map-tools
  ros-humble-rmf-api-msgs ros-humble-rmw-cyclonedds-cpp
  ros-humble-rmf-visualization-navgraphs ros-humble-rmf-visualization-fleet-states
  ros-humble-rmf-visualization-schedule ros-humble-nav2-msgs
  ros-humble-nav2-rviz-plugins ros-humble-controller-manager-msgs
)
export LC_ALL=C
if [[ $mode == --install ]]; then
  [[ $EUID == 0 ]] || {
    printf '%s\n' 'Run: sudo bash main/install-dependencies.bash --install' >&2
    exit 2
  }
  apt-get update
fi
plan=$(apt-get --simulate --no-remove --no-install-recommends --no-upgrade install "${packages[@]}")
printf '%s\n' "$plan"
if [[ $mode == --check ]]; then
  exit 0
fi
# An installed-version bracket on an Inst line means an existing package changes.
if [[ $plan =~ Inst\ [^[:space:]]+\ \[ || $plan == *$'\nRemv '* ]]; then
  printf '%s\n' 'Existing packages would change. Review the apt plan before continuing.' >&2
  exit 2
fi
apt-get --assume-yes --no-remove --no-install-recommends --no-upgrade install "${packages[@]}"
printf '%s\n' 'RMF core dependencies installed. Build with: bash tools/main.bash build'
