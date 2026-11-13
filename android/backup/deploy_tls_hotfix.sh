#!/usr/bin/env bash
# Run AS ROOT INSIDE LXC 120 after updating its settings-web worktree.
# Never reads, exports or changes the bearer token or game saves.
set -euo pipefail

repo=/srv/ffbe-distribution/build-cache/settings-web-worktree
src="$repo/android/backup/lxc_backup.py"
dest=/usr/local/libexec/ffbe-backup/lxc_backup.py
rollback="/srv/ffbe-distribution/build-cache/ffbe-backup-receiver-before-tls-fix-$(date +%Y%m%d%H%M%S).py"

[ "$(id -u)" -eq 0 ] || { echo "Run as root in LXC 120" >&2; exit 1; }
mountpoint -q /var/lib/ffbe-save-backups || {
  echo "ABORT: external ZFS backup volume not mounted" >&2; exit 1;
}
test -f "$src" && test -f "$dest"
python3 - "$src" <<'PY'
import ast, pathlib, sys
source = pathlib.Path(sys.argv[1]).read_text('utf-8')
ast.parse(source)
assert 'class ThreadingTLSHTTPServer' in source
assert 'ThreadingTLSHTTPServer((args.bind, args.port)' in source
print('TLS hotfix code validated')
PY
cp -p "$dest" "$rollback"
install -o root -g root -m 0555 "$src" "$dest"

if systemctl restart ffbe-save-backup.service   && systemctl is-active --quiet ffbe-save-backup.service   && [ "$(curl --noproxy '*' --cacert /etc/ffbe-backup/cert.pem -sS --max-time 8         -o /dev/null -w '%{http_code}'         https://192.168.15.230:18447/v1/backups/samsung-android)" = 401 ]; then
  echo "SUCCESS: ffbe-save-backup active, TLS verified, protected API returns HTTP 401"
  echo "Rollback snapshot: $rollback"
else
  echo "FAILED: restoring previous receiver" >&2
  install -o root -g root -m 0555 "$rollback" "$dest"
  systemctl restart ffbe-save-backup.service || true
  exit 1
fi
