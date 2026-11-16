#!/usr/bin/env bash
# Install/enable at boot; do not start or restart an existing navigation session.
set -euo pipefail
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
[[ $(id -un) == husky && $repo_dir == /home/husky/rmf-integration ]] || {
  printf '%s\n' 'Run this installer as husky in /home/husky/rmf-integration.' >&2; exit 2;
}
bash "$repo_dir/tools/husky_bringup.bash" prepare
backup="$repo_dir/husky/log/validation/boot_install_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$backup" "$HOME/.config/systemd/user"
unit="$HOME/.config/systemd/user/brin-husky-bringup.service"
[[ ! -e $unit ]] || cp -p "$unit" "$backup/service.before"
install -m 0644 "$repo_dir/husky/systemd/brin-husky-bringup.service" "$unit"
systemd-analyze --user verify "$unit"
systemctl --user daemon-reload
systemctl --user enable brin-husky-bringup.service
if [[ $(loginctl show-user husky -p Linger --value) != yes ]]; then
  loginctl enable-linger husky
fi
[[ $(loginctl show-user husky -p Linger --value) == yes ]]
printf '%s\n' 'Enabled at boot, including without desktop login. Not started by installer.' \
  'Start: systemctl --user start brin-husky-bringup.service' \
  'Status: systemctl --user status brin-husky-bringup.service' \
  'Logs: journalctl --user -u brin-husky-bringup.service -f'
