#!/usr/bin/env bash
# Per-user Python runtime; does not install system packages or start services.
set -euo pipefail
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
web_root=${RMF_WEB_ROOT:-/home/rslab/rmf-web}
expected=e2861c292bb27014435452e74faa825ecb0e8d91
[[ $(git -C "$web_root" rev-parse HEAD) == "$expected" ]] || {
  printf '%s\n' 'Unexpected RMF Web revision; review before installing.' >&2
  exit 2
}
python3 -m venv --system-site-packages "$web_root/.venv"
python="$web_root/.venv/bin/python"
"$python" -m pip install --disable-pip-version-check --no-input -r "$repo_dir/main/web/python-requirements.txt"
"$python" -m pip install --disable-pip-version-check --no-input --no-deps \
  -e "$web_root/packages/ros-translator" -e "$web_root/packages/api-server"
printf '%s\n' 'RMF Web Python runtime installed.'
