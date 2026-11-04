#!/usr/bin/env bash
# Start only the existing RMF dashboard; API/core/robot processes are separate.
set -euo pipefail
mode=${1:-lan}
if [[ $# -gt 1 ]]; then
  printf '%s\n' 'Usage: bash tools/dashboard.bash [lan|local|--help]' >&2
  exit 2
fi
case "$mode" in
  lan) dashboard_host=0.0.0.0 ;;
  local) dashboard_host=127.0.0.1 ;;
  --help)
    printf '%s\n' 'Usage: bash tools/dashboard.bash [lan|local]' \
      'lan (default): listen on port 3000 for devices on the same network.' \
      'local: listen on 127.0.0.1:3000 for this laptop only.' \
      'Optional: BRIN_LAPTOP_IP, RMF_WEB_ROOT, BRIN_WEB_BROWSER_API_URL, BRIN_WEB_BROWSER_TRAJECTORY_URL.'
    exit 0 ;;
  *) printf 'Unknown dashboard mode: %s\n' "$mode" >&2; exit 2 ;;
esac
export BRIN_LAPTOP_IP="${BRIN_LAPTOP_IP:-192.168.0.218}"
export RMF_WEB_ROOT="${RMF_WEB_ROOT:-/mnt/UbuntuData/rmf-web}"
dashboard_node="$RMF_WEB_ROOT/.brin-tools/node-v16.20.2-linux-x64/bin/node"
dashboard_pnpm="$RMF_WEB_ROOT/.brin-tools/pnpm/node_modules/.bin/pnpm"
[[ -x $dashboard_node && -x $dashboard_pnpm ]] || {
  printf 'Dashboard runtime is incomplete under %s\n' "$RMF_WEB_ROOT" >&2
  exit 2
}
export PATH="$(dirname -- "$dashboard_node"):$(dirname -- "$dashboard_pnpm"):$PATH"
export HOST="$dashboard_host" PORT=3000 BROWSER=none
export REACT_APP_RMF_SERVER="${BRIN_WEB_BROWSER_API_URL:-http://$BRIN_LAPTOP_IP:8000}"
export REACT_APP_TRAJECTORY_SERVER="${BRIN_WEB_BROWSER_TRAJECTORY_URL:-ws://$BRIN_LAPTOP_IP:8006}"
if [[ $mode == lan ]]; then
  printf 'Dashboard URL: http://%s:3000\n' "$BRIN_LAPTOP_IP"
else
  printf '%s\n' 'Dashboard URL: http://127.0.0.1:3000'
fi
cd -- "$RMF_WEB_ROOT"
exec "$dashboard_pnpm" --filter rmf-dashboard run start:react
