#!/usr/bin/env bash
# Install only this project's user units and desktop autostart entry.
set -euo pipefail
[[ $(id -un) == rslab && $EUID != 0 ]] || {
  printf '%s\n' 'Run as rslab, without sudo, on komputer-utama.' >&2
  exit 2
}
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
[[ $repo_dir == /home/rslab/rmf-integration ]] || exit 2
[[ -f $repo_dir/main/install/local_setup.bash ]] || exit 2
[[ -x /home/rslab/rmf-web/.venv/bin/python ]] || exit 2
[[ -f $repo_dir/main/log/web/dashboard/index.html ]] || {
  printf '%s\n' 'Build the production dashboard first.' >&2
  exit 2
}
systemd-analyze --user verify "$repo_dir"/main/systemd/brin-rmf*.service "$repo_dir/main/systemd/brin-rmf.target"
if command -v desktop-file-validate >/dev/null; then
  desktop-file-validate "$repo_dir/main/desktop/brin-rmf.desktop"
fi
unit_dir=/home/rslab/.config/systemd/user
autostart_dir=/home/rslab/.config/autostart
backup="$repo_dir/main/log/bringup-backup-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$unit_dir" "$autostart_dir" "$backup"
for source in "$repo_dir"/main/systemd/brin-rmf*.service "$repo_dir/main/systemd/brin-rmf.target"; do
  destination="$unit_dir/$(basename -- "$source")"
  if [[ -f $destination ]] && ! cmp -s "$source" "$destination"; then
    cp -p "$destination" "$backup/$(basename -- "$destination")"
  fi
  install -m 644 "$source" "$destination"
done
desktop="$autostart_dir/brin-rmf.desktop"
if [[ -f $desktop ]] && ! cmp -s "$repo_dir/main/desktop/brin-rmf.desktop" "$desktop"; then
  cp -p "$desktop" "$backup/brin-rmf.desktop"
fi
install -m 644 "$repo_dir/main/desktop/brin-rmf.desktop" "$desktop"
systemctl --user daemon-reload
systemctl --user enable brin-rmf.target brin-rmf-core.service brin-rmf-web-api.service brin-rmf-dashboard.service
printf 'BRINGUP_CONFIG_BACKUP=%s\n' "$backup"
printf '%s\n' 'Bringup units and desktop autostart installed.'
