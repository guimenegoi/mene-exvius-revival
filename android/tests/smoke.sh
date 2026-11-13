#!/usr/bin/env bash
# Non-destructive smoke tests for the CLI without game assets.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
RUNNER="$ROOT/android/ffbe-termux"
TMP="$(mktemp -d)"
trap 'rm -rf -- "$TMP"' EXIT
bash -n "$RUNNER"
bash -n "$ROOT/android/build-package.sh"
env FFBE_ANDROID_HOME="$TMP" FFBE_DATA_DIR="$TMP/data" "$RUNNER" help >"$TMP/help.log"
grep -q 'fetch-data' "$TMP/help.log"
env FFBE_ANDROID_HOME="$TMP" FFBE_DATA_DIR="$TMP/data" "$RUNNER" status >"$TMP/status.log"
grep -q 'não está ativo' "$TMP/status.log"
if env FFBE_ANDROID_HOME="$TMP" FFBE_DATA_DIR="$TMP/data" "$RUNNER" start >"$TMP/start.log" 2>&1; then
  echo 'ERROR: start accepted missing game assets' >&2
  exit 1
fi
if env FFBE_ANDROID_HOME="$TMP" FFBE_HTTP_PORT=80 "$RUNNER" doctor >"$TMP/doctor.log" 2>&1; then
  echo 'ERROR: doctor accepted privileged port 80' >&2
  exit 1
fi
grep -q 'Porta fora do intervalo' "$TMP/doctor.log"
test ! -e "$TMP/server-root/state/campaign.json"
# Reuse all existing Android test suites; no second test runner or APK build.
for suite in runtime data distribution network backup; do
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
    -s "$ROOT/android/$suite" -p 'test_*.py' -q
done
echo 'OK: CLI guards, isolated state, runtime, data, distribution, network and backup tests'
