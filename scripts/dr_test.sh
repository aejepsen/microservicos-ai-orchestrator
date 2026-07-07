#!/usr/bin/env bash
# FASE 15 — teste de DR reproduzível: ingest canary → backup → apaga coleção
# (simula perda) → restore → confirma que o canary voltou. Mede RTO.
set -euo pipefail

cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
KEY="${QDRANT_API_KEY:?}"; IKEY="${INTERNAL_KEY:?}"
NET="${BACKUP_NET:-msvc-prod-backend}"
COL="${DR_COLLECTION:-financas}"
qc() { docker run --rm --network "$NET" curlimages/curl:latest -s "$@"; }

echo "== 1. ingest canary em '$COL' =="
curl -s -X POST http://127.0.0.1:8204/v1/ingest -H "X-Internal-Key: $IKEY" \
  -H 'Content-Type: application/json' \
  -d "{\"collection\":\"$COL\",\"documents\":[{\"id\":\"dr-canary\",\"text\":\"CANARY DR: faturamento trimestre R\$ 1.250.000,00\"}]}" >/dev/null

echo "== 2. backup =="
./scripts/backup.sh >/dev/null

echo "== 3. simula perda: apaga a coleção =="
qc -X DELETE "http://qdrant:6333/collections/$COL" -H "api-key: $KEY" >/dev/null

echo "== 4. restore (RTO) =="
t0=$(date +%s.%N); ./scripts/restore.sh >/dev/null; t1=$(date +%s.%N)
sleep 2

echo "== 5. verifica canary =="
curl -s -X POST http://127.0.0.1:8204/v1/search -H "X-Internal-Key: $IKEY" \
  -H 'Content-Type: application/json' \
  -d "{\"collection\":\"$COL\",\"query\":\"faturamento trimestre\",\"top_k\":3}" \
  | python3 -c '
import json,sys
r=json.load(sys.stdin); hits=r.get("results") or r.get("hits") or []
assert hits and any("CANARY DR" in h.get("text","") for h in hits), "DR FALHOU: canary nao voltou"
print("DR TEST OK: canary recuperado")
'
echo "RTO_restore=$(echo "$t1-$t0" | bc)s"
