#!/usr/bin/env bash
# FASE 15 — restore do Qdrant a partir de um backup do backup.sh.
# Sobe cada .snapshot via upload API (priority=snapshot: substitui a coleção).
#
# Uso: ./scripts/restore.sh [BACKUP_DIR/timestamp]
#   sem argumento → usa o backup mais recente em ./backups
set -euo pipefail

cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
KEY="${QDRANT_API_KEY:?QDRANT_API_KEY ausente (.env)}"
NET="${BACKUP_NET:-msvc-prod-backend}"
QDRANT_CT="${QDRANT_CT:-msvc-prod-qdrant-1}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"

qapi() { docker run --rm --network "$NET" curlimages/curl:latest -s "$@" -H "api-key: $KEY"; }

SRC="${1:-$(ls -1d "$BACKUP_DIR"/*/ 2>/dev/null | sort | tail -1)}"
[ -n "$SRC" ] && [ -d "$SRC" ] || { echo "backup não encontrado: $SRC"; exit 1; }
SRC="${SRC%/}"
echo "== restore Qdrant <- $SRC =="

shopt -s nullglob
snaps=("$SRC"/*.snapshot)
[ "${#snaps[@]}" -gt 0 ] || { echo "sem .snapshot em $SRC"; exit 1; }

for f in "${snaps[@]}"; do
  c="$(basename "$f" .snapshot)"
  echo "-- restore $c ($(stat -c%s "$f") bytes)"
  # upload API (multipart/HTTP): não toca o filesystem do container, então não
  # esbarra no cap_drop:ALL do hardening (SEC). priority=snapshot substitui a coleção.
  docker run --rm --network "$NET" -v "$(pwd)/$SRC:/in:ro" curlimages/curl:latest -s \
    --max-time 120 -w '\n   HTTP %{http_code}\n' \
    -X POST "http://qdrant:6333/collections/$c/snapshots/upload?priority=snapshot" \
    -H "api-key: $KEY" -F "snapshot=@/in/$c.snapshot"
done
echo "== restore OK =="
