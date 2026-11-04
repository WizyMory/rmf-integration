#!/usr/bin/env bash
# Run with sudo on Devi AFTER reviewing the prepared override.
# Install/enable only. Existing manual bringup must be stopped before starting.
set -euo pipefail
if [[ $EUID != 0 ]]; then
  printf '%s\n' 'Run with sudo bash devi/systemd/install.bash on Devi.' >&2
  exit 2
fi
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
[[ $repo_dir == /home/devi/rmf-integration ]] || { printf '%s\n' 'This installer is only for the Devi robot workspace.' >&2; exit 2; }
[[ -f $repo_dir/devi/install/local_setup.bash ]] || { printf '%s\n' 'Build the Devi integration first.' >&2; exit 2; }
backup_dir="$repo_dir/devi/log/service_backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$backup_dir"
systemctl cat devi_robot.service > "$backup_dir/devi_robot.service.before.txt"
desktop=/home/devi/.config/autostart/gnome-terminal.desktop
if [[ -f $desktop ]]; then
  cp -p "$desktop" "$backup_dir/gnome-terminal.desktop.before"
  # This old entry launches the same hardware/Nav2 stack after GUI login.
  # Disable only the exact reviewed entry; retain its backup and script.
  python3 - "$desktop" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text()
if '/home/devi/devi_autostart.sh' not in text:
    raise SystemExit('Autostart entry differs from the reviewed Devi entry; review before installing')
lines = [line for line in text.splitlines() if not line.startswith(('Hidden=', 'X-GNOME-Autostart-enabled='))]
lines.extend(['Hidden=true', 'X-GNOME-Autostart-enabled=false'])
path.write_text('\n'.join(lines) + '\n')
PY
fi
if [[ -f /etc/systemd/system/devi_robot.service.d/rmf-integration.conf ]]; then
  cp /etc/systemd/system/devi_robot.service.d/rmf-integration.conf "$backup_dir/override.before.conf"
fi
# Stop the failing old service before reloading; otherwise its retry loop may
# launch the new stack alongside the operator's still-running manual bringup.
systemctl stop devi_robot.service
install -D -m 0644 "$repo_dir/devi/systemd/rmf-integration.conf" \
  /etc/systemd/system/devi_robot.service.d/rmf-integration.conf
systemctl daemon-reload
systemctl enable devi_robot.service
printf '%s\n' 'Installed and enabled for boot. Service has NOT been started.' \
  'Stop the old manual bringup terminal first, then run: sudo systemctl start devi_robot.service' \
  "Backup: $backup_dir"
