#!/usr/bin/env bash
set -euo pipefail
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
set -a
source "$repo_dir/main/config/bringup.env"
set +a
[[ $(git -C "$RMF_WEB_ROOT" rev-parse HEAD) == e2861c292bb27014435452e74faa825ecb0e8d91 ]] || exit 2
export PATH="$RMF_WEB_ROOT/.brin-tools/node-v16.20.2-linux-x64/bin:$RMF_WEB_ROOT/.brin-tools/pnpm/node_modules/.bin:$PATH"
export NODE_ENV=production CI=false SKIP_PREFLIGHT_CHECK=true GENERATE_SOURCEMAP=false
export PUBLIC_URL=/ BUILD_PATH="$repo_dir/main/log/web/dashboard.next"
export REACT_APP_RMF_SERVER="http://$BRIN_MAIN_IP:8000"
export REACT_APP_TRAJECTORY_SERVER="ws://$BRIN_MAIN_IP:8006"
mkdir -p "$repo_dir/main/log/web"
cd "$RMF_WEB_ROOT"
pnpm run --filter 'rmf-dashboard^...' build
source_dir="$repo_dir/main/log/web/dashboard-source"
python3 "$repo_dir/main/web/prepare_dashboard.py" "$RMF_WEB_ROOT" "$source_dir"
cd "$source_dir"
node "$RMF_WEB_ROOT/packages/dashboard/node_modules/react-scripts/scripts/build.js"
[[ -f $BUILD_PATH/index.html ]] || exit 2
destination="$repo_dir/main/log/web/dashboard"
if [[ -e $destination ]]; then
  mv "$destination" "$destination.backup-$(date -u +%Y%m%dT%H%M%SZ)"
fi
mv "$BUILD_PATH" "$destination"
printf 'DASHBOARD_BUILD=%s\n' "$destination"
