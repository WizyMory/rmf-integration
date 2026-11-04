#!/usr/bin/env bash
# Isolated public preview. Never starts an unauthenticated tunnel.
set -euo pipefail
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
web_root=${RMF_WEB_ROOT:-/mnt/UbuntuData/rmf-web}
runtime="$repo_root/laptop/log/rmf_web_public"
overlay="$repo_root/laptop/src/brin_husky_distributed/web"
proxy_image='nginx@sha256:0e52bd054126cdc040b1276c0af347aeb02a41b9cfe305d6094767ac30e97949'
container_name=brin-rmf-public
cloudflared="$runtime/bin/cloudflared"
mode=${1:---help}
case "$mode" in
  --help)
    printf '%s\n' 'Usage: bash tools/web_public.bash prepare' \
      '       bash tools/web_public.bash start EMAIL' \
      'Requires running laptop API/core, Docker, and the audited rmf-web checkout.'
    exit 0 ;;
  prepare|start) ;;
  *) printf 'Unknown mode: %s\n' "$mode" >&2; exit 2 ;;
esac
mkdir -p "$runtime/bin" "$runtime/webroot"
exec 9>"$runtime/launcher.lock"
flock -n 9 || { printf '%s\n' 'Public dashboard launcher already running.' >&2; exit 2; }
if [[ $mode == prepare ]]; then
  [[ $# == 1 ]] || { printf '%s\n' 'prepare does not accept extra arguments.' >&2; exit 2; }
  python3 - "$cloudflared" <<'PY'
import hashlib
from pathlib import Path
import sys
import urllib.request
path = Path(sys.argv[1])
expected = '1f99fb518b83dec2ba8d870a7cc991d82a77e6196295a3d2754ba17ab9f91872'
if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
    temporary = path.with_suffix('.download')
    urllib.request.urlretrieve('https://github.com/cloudflare/cloudflared/releases/download/2026.10.7/cloudflared-linux-amd64', temporary)
    if hashlib.sha256(temporary.read_bytes()).hexdigest() != expected:
        temporary.unlink()
        raise SystemExit('cloudflared checksum mismatch; refusing to continue')
    temporary.chmod(0o755)
    temporary.replace(path)
print('cloudflared 2026.10.7 checksum verified')
PY
  docker image inspect "$proxy_image" >/dev/null 2>&1 || docker pull "$proxy_image"
  python3 "$repo_root/tools/prepare_public_dashboard.py" "$web_root" "$runtime" "$overlay"
  exit 0
fi
[[ $# == 2 ]] || { printf '%s\n' 'start requires one allowed email address.' >&2; exit 2; }
allowed_email=$2
api_host=${BRIN_LAPTOP_IP:-192.168.0.218}
python3 - "$allowed_email" "$api_host" <<'PY'
import ipaddress, re, sys
if not re.fullmatch(r'[A-Za-z0-9._+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', sys.argv[1]):
    raise SystemExit('Specify one complete allowed email address; wildcards are not accepted.')
if ipaddress.ip_address(sys.argv[2]).version != 4:
    raise SystemExit('BRIN_LAPTOP_IP must be the laptop IPv4 LAN address.')
PY
[[ -x $cloudflared && -f $runtime/webroot/dashboard/index.html ]] || {
  printf '%s\n' 'Run bash tools/web_public.bash prepare first.' >&2; exit 2;
}
help_text=$("$cloudflared" tunnel --help)
[[ $help_text == *'--allowed-mail'* ]] || {
  printf '%s\n' 'This cloudflared cannot enforce email login; refusing to publish.' >&2; exit 2;
}
if docker container inspect "$container_name" >/dev/null 2>&1; then
  printf '%s\n' 'brin-rmf-public already exists; inspect its owner before restarting.' >&2
  exit 2
fi
python3 - "$overlay/public-nginx.conf" "$runtime/nginx.conf" "$api_host" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[2]).write_text(Path(sys.argv[1]).read_text().replace('__BRIN_API_HOST__', sys.argv[3]))
PY
printf '{}\n' >"$runtime/cloudflared-empty.yaml"
docker_args=(--rm --name "$container_name" --network host --user "$(id -u):$(id -g)"
  --read-only --cap-drop ALL --security-opt no-new-privileges
  --tmpfs /tmp:rw,noexec,nosuid,size=32m
  --mount "type=bind,src=$runtime/webroot,dst=/srv,readonly"
  --mount "type=bind,src=$runtime/nginx.conf,dst=/etc/nginx/nginx.conf,readonly"
  --entrypoint nginx "$proxy_image")
docker run "${docker_args[@]}" -t
proxy_started=false
tunnel_pid=
cleanup() {
  trap - EXIT INT TERM
  if [[ -n $tunnel_pid ]]; then
    kill "$tunnel_pid" 2>/dev/null || true
    wait "$tunnel_pid" 2>/dev/null || true
  fi
  if [[ $proxy_started == true ]]; then
    docker stop -t 5 "$container_name" >/dev/null 2>&1 || true
  fi
  rm -f "$runtime/public_url.txt"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
docker run -d "${docker_args[@]}" -g 'daemon off;' >/dev/null
proxy_started=true
python3 - <<'PY'
import time, urllib.error, urllib.request
for url in ('http://127.0.0.1:8088/', 'http://127.0.0.1:8088/api/fleets'):
    for attempt in range(10):
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    break
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(1)
    else:
        raise SystemExit('Gateway/API not ready; refusing to publish')
PY
printf '%s\n' 'Starting email-protected Cloudflare preview. Ctrl-C stops only this gateway and tunnel.'
env -u TUNNEL_TOKEN -u TUNNEL_CRED_FILE -u TUNNEL_HOSTNAME -u TUNNEL_ORIGIN_CERT \
  "$cloudflared" tunnel --config "$runtime/cloudflared-empty.yaml" --no-autoupdate \
  --url http://127.0.0.1:8088 --allowed-mail "$allowed_email" \
  >"$runtime/tunnel.log" 2>&1 &
tunnel_pid=$!
for ((attempt=0; attempt<60; attempt++)); do
  kill -0 "$tunnel_pid" 2>/dev/null || { tail -n 15 "$runtime/tunnel.log"; exit 1; }
  public_url=$(sed -nE '/https:\/\/(api|login)\.trycloudflare\.com/!s@.*(https://[a-z0-9-]+\.trycloudflare\.com).*@\1@p' "$runtime/tunnel.log" | head -n 1)
  if [[ -n $public_url ]]; then
    printf '%s\n' "$public_url" >"$runtime/public_url.txt"
    printf 'Public dashboard: %s\nLogin: email one-time PIN; only the supplied email is allowed.\n' "$public_url"
    wait "$tunnel_pid"
    exit $?
  fi
  sleep 1
done
printf '%s\n' 'Timed out creating protected tunnel; inspect laptop/log/rmf_web_public/tunnel.log.' >&2
exit 1
