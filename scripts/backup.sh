#!/usr/bin/env bash
# FASE 15 — backup do estado de negócio (Qdrant) via snapshot API.
#
# Por que só Qdrant: é o único dado insubstituível (vetores RAG). Grafana e
# Prometheus são recuperáveis (dashboards/datasources versionados em git;
# métricas são lossy-ok). Ollama = redownload. Jaeger = traces efêmeros.
# Config do stack (compose, provisioning) já vive no git.
#
# Snapshot API dá cópia consistente sem parar o serviço. Os arquivos ficam em
# /qdrant/snapshots (efêmero) — copiamos com `docker cp` pro BACKUP_DIR (o
# endpoint de download HTTP retorna 0 bytes nesta versão do Qdrant).
#
# Uso: ./scripts/backup.sh   (BACKUP_DIR=./backups por default, RETAIN=7)
set -euo pipefail

cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
KEY="${QDRANT_API_KEY:?QDRANT_API_KEY ausente (.env)}"
NET="${BACKUP_NET:-msvc-prod-backend}"
QDRANT_CT="${QDRANT_CT:-msvc-prod-qdrant-1}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETAIN="${RETAIN:-7}"
STAMP="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
DEST="$BACKUP_DIR/$STAMP"

qapi() { docker run --rm --network "$NET" curlimages/curl:latest -s "$@" -H "api-key: $KEY"; }

mkdir -p "$DEST"
echo "== backup Qdrant -> $DEST =="

cols=$(qapi http://qdrant:6333/collections \
  | python3 -c 'import json,sys; print(" ".join(c["name"] for c in json.load(sys.stdin)["result"]["collections"]))')
[ -z "$cols" ] && { echo "nenhuma coleção — nada a fazer"; exit 0; }

manifest="$DEST/manifest.txt"
echo "timestamp=$STAMP" > "$manifest"
for c in $cols; do
  echo "-- snapshot $c"
  snap=$(qapi -X POST "http://qdrant:6333/collections/$c/snapshots" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["name"])')
  docker cp "$QDRANT_CT:/qdrant/snapshots/$c/$snap" "$DEST/$c.snapshot"
  # Qdrant cria o snapshot em mode 600; 644 permite o container de restore lê-lo
  chmod 644 "$DEST/$c.snapshot"
  sz=$(stat -c%s "$DEST/$c.snapshot" 2>/dev/null || echo 0)
  echo "$c=$snap size=$sz" >> "$manifest"
  echo "   copiado: $c.snapshot ($sz bytes)"
  qapi -X DELETE "http://qdrant:6333/collections/$c/snapshots/$snap" >/dev/null || true
done

# retenção: mantém os RETAIN backups mais recentes
mapfile -t all < <(ls -1d "$BACKUP_DIR"/*/ 2>/dev/null | sort)
if [ "${#all[@]}" -gt "$RETAIN" ]; then
  for old in "${all[@]:0:$((${#all[@]}-RETAIN))}"; do
    echo "-- retenção: removendo $old"; rm -rf "$old"
  done
fi

echo "== backup OK: $(cat "$manifest" | tr '\n' ' ')"
echo "$DEST"
