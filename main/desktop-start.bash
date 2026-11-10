#!/usr/bin/env bash
# GNOME invokes this with the authenticated desktop's display environment.
set -euo pipefail
variables=()
for variable in DISPLAY XAUTHORITY WAYLAND_DISPLAY XDG_SESSION_TYPE XDG_CURRENT_DESKTOP; do
  [[ -z ${!variable:-} ]] || variables+=("$variable")
done
if [[ ${#variables[@]} -gt 0 ]]; then
  systemctl --user import-environment "${variables[@]}"
fi
systemctl --user start brin-rmf.target
systemctl --user start brin-rmf-rviz.service brin-rmf-browser.service
