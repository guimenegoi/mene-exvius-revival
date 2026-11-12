#!/usr/bin/env bash
# Build a source-only local preview from a clean Git commit.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
[[ -z "$(git status --porcelain)" ]] || {
  echo 'Erro: há arquivos modificados. Faça commit antes de empacotar.' >&2
  exit 1
}
VERSION="$(git rev-parse --short=8 HEAD)"
OUT="$ROOT/dist"
ARCHIVE="$OUT/mene-exvius-revival-termux-$VERSION.tar.gz"
mkdir -p "$OUT"
git archive --format=tar --prefix=mene-exvius-revival/ HEAD | gzip -n -9 > "$ARCHIVE"
sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"
echo "Pacote de código: $ARCHIVE"
echo 'Conteúdo: checkout e scripts Termux, SEM dados de jogo, APK ou saves.'
echo 'O pacote não é uma release jogável nem é enviado automaticamente ao GitHub.'
