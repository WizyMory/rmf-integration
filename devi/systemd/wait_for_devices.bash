#!/usr/bin/env bash
# Wait for the existing aliases used by the reviewed driver parameters/udev.
# The old desktop script checked /dev/tty-ROBOTEQ; the actual port is /dev/Roboteq.
for device in /dev/Roboteq /dev/rplidar; do
  for ((attempt=0; attempt<30; attempt++)); do
    [[ -e $device ]] && break
    sleep 1
  done
  [[ -e $device ]] || printf 'Warning: %s not found after device wait\n' "$device"
done
exit 0
