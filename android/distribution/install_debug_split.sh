#!/usr/bin/env bash
# Laboratório FFBE Android 9.1.0. Atualiza sem desinstalar ou limpar saves.
set -Eeuo pipefail
cd "$(dirname "$0")"
ADB="${ADB:-adb}"
command -v "$ADB" >/dev/null || { echo "adb não encontrado" >&2; exit 1; }
for name in base.apk config.arm64_v8a.apk config.en.apk config.fr.apk config.mdpi.apk; do
  test -s "apk/$name" || { echo "Falta apk/$name" >&2; exit 1; }
done
if [ -f apk/SHA256SUMS ]; then
  (cd apk && sha256sum -c SHA256SUMS >/dev/null)
  echo "Hashes dos cinco APKs conferidos."
fi
echo "FFBE Revival — instalação experimental. Não limpa dados."
"$ADB" install-multiple -r \
  apk/base.apk \
  apk/config.arm64_v8a.apk \
  apk/config.en.apk \
  apk/config.fr.apk \
  apk/config.mdpi.apk
echo "Splits atualizados. APK ainda exige instalador de primeiro uso."
