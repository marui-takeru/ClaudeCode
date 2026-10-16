#!/bin/sh
# 公開リポジトリ (MiniShikoku3d) へページ一式をコピーする。
# README.md は公開用に別管理なのでコピーしない。
set -eu
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$SRC/../../minishikoku3d}"
cp "$SRC/index.html" "$SRC/DATA_SOURCES.md" "$SRC/CHANGELOG.md" "$DEST/"
for d in css js data; do
  mkdir -p "$DEST/$d"
  cp "$SRC/$d/"* "$DEST/$d/"
done
echo "synced to $DEST"
