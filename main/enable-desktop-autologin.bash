#!/usr/bin/env bash
# GUI-on-boot requires the existing GNOME desktop to log in automatically.
set -euo pipefail
[[ $EUID == 0 ]] || { printf '%s\n' 'Run with sudo on komputer-utama.' >&2; exit 2; }
[[ $# == 0 ]] || exit 2
python3 - <<'PY'
from datetime import datetime, timezone
import os
from pathlib import Path
import pwd
import re
import tempfile

user = pwd.getpwnam('rslab')
if user.pw_dir != '/home/rslab' or user.pw_uid == 0:
    raise SystemExit('Unexpected desktop account.')
path = Path('/etc/gdm3/custom.conf')
if path.is_symlink() or not path.is_file():
    raise SystemExit('Review the GDM config path before changing it.')
original = path.read_bytes()
text = original.decode()
headers = list(re.finditer(r'(?m)^\[([^\]]+)\][ \t]*$', text))
daemon = [h for h in headers if h.group(1) == 'daemon']
if len(daemon) != 1:
    raise SystemExit('Expected one GDM daemon section.')
start = daemon[0].end()
end = next((h.start() for h in headers if h.start() > start), len(text))
section = text[start:end]
for key, value in (('AutomaticLoginEnable', 'true'), ('AutomaticLogin', 'rslab')):
    pattern = rf'(?m)^[ \t]*{key}[ \t]*=[^\n]*$'
    matches = list(re.finditer(pattern, section))
    if len(matches) > 1:
        raise SystemExit('Multiple active GDM values require review: ' + key)
    section = re.sub(pattern, f'{key} = {value}', section) if matches else section.rstrip() + f'\n{key} = {value}\n\n'
updated = (text[:start] + section + text[end:]).encode()
if updated == original:
    print('Automatic desktop login for rslab is already configured.')
    raise SystemExit(0)
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup = path.with_name(path.name + '.brin-rmf-backup-' + stamp)
fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
with os.fdopen(fd, 'wb') as stream:
    stream.write(original)
stat = path.stat()
temporary = None
try:
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.brin-rmf-gdm-', delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(updated)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(stat.st_mode & 0o777)
    os.chown(temporary, stat.st_uid, stat.st_gid)
    os.replace(temporary, path)
finally:
    if temporary is not None and temporary.exists():
        temporary.unlink()
print('BACKUP=' + str(backup))
print('AUTOMATIC_DESKTOP_LOGIN=rslab')
print('Configuration applies on the next desktop login/boot.')
PY
