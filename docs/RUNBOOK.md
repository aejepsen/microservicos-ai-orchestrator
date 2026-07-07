# Runbook — Troubleshooting

Problemas reais observados neste stack e como diagnosticar/corrigir. Cada item começa
pelo sintoma. Convenção: `source .env` primeiro; `$KEY` = `$INTERNAL_KEY`.

## Diagnóstico rápido

```bash
make ps                                   # quem está unhealthy
docker compose -f docker-compose.prod.yml logs --tail=50 svc-<nome>
curl -s http://127.0.0.1:8206/health | python3 -m json.tool   # deps do orchestrator
```

O `/health` do orchestrator agrega o estado dos downstreams — é o primeiro lugar a olhar.

---

## `/v1/chat` retorna 503 "downstream router indisponivel"

**Causa comum 1 — embedder do router/guardrails caiu (`llm_adapter`/`embedder: down`).**
Rede `backend` é `internal` (sem DNS externo); se faltar `HF_HUB_OFFLINE=1`, o
SentenceTransformer tenta bater no huggingface.co no boot e falha mesmo com o modelo
em cache.
```bash
curl -s http://127.0.0.1:8203/health   # (via exec, porta interna) embedder: ok?
docker logs msvc-prod-svc-router-1 | grep -i 'embedder\|offline'
```
Fix: garantir `HF_HUB_OFFLINE: "1"` no serviço (compose). Já aplicado em guardrails/router/rag.

**Causa comum 2 — router sem fallback LLM e query ambígua.**
Se a query não roteia por semântica e o fallback LLM está `disabled`, o router dá 503.
Confirme `LLM_ENABLED=1` + `LLM_URL=http://svc-inference:8202/v1/chat/completions`
+ `DOWNSTREAM_KEY` no compose (o `HttpLLM` envia `X-Internal-Key`).

## `/v1/chat` retorna 403

Esperado para prompt injection — o guardrails bloqueia (fail-closed). Se for query
legítima marcada como injection: ver "OOD false positive" abaixo.

## `/v1/chat` retorna 401

Falta ou está errada a `X-Internal-Key`. Confirme que o header casa com `INTERNAL_KEY`
do `.env`. Comparação é timing-safe (`hmac.compare_digest`).

## `/v1/chat` retorna 422

Input rejeitado por validação — provável `query` acima de `max_length=8000` (proteção
DoS/custo, SEC-02) ou JSON malformado. O corpo do erro indica o campo.

## Chat muito lento / P95 > 5s

O gargalo é a geração LLM na GPU única (esperado — ver baseline `NEXT_PHASES §14.3`).
```bash
docker exec msvc-prod-ollama-1 ollama ps        # modelo carregou? 100% GPU?
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader
```
- Modelo descarregado → primeiro request paga cold start (~12s). Depois `KEEP_ALIVE=5m`.
- Modelo em CPU (`ollama ps` mostra CPU) → GPU não passou ao container; ver runtime NVIDIA.
- Concorrência de chat > 1 degrada forte (1 GPU serializa). Capacidade real ≈ 1 chat
  concorrente. Escalar = mais GPUs, não tuning.

## Trace não aparece no Jaeger

```bash
docker logs msvc-prod-svc-orchestrator-1 | grep -i 'otel'    # "OTel traces ativo"?
```
- Confirme `OTEL_ENABLED=1` + `OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318`.
- O `BatchSpanProcessor` faz flush em lote — aguarde alguns segundos após a request.
- `/health` e `/metrics` são excluídos dos spans de propósito (`excluded_urls`).

## Prometheus target down

```bash
curl -s http://127.0.0.1:9090/api/v1/targets | python3 -m json.tool | grep -A2 health
```
O Prometheus raspa **só** o svc-observability (`/v1/prometheus`), autenticado via
arquivo de chave. Se `up == 0`: verifique o svc-observability e se o `INTERNAL_KEY`
bateu no entrypoint do Prometheus.

## Circuit breaker preso OPEN

O orchestrator abre o circuito de um downstream após `CIRCUIT_FAIL_THRESHOLD=5` falhas;
transiciona para HALF_OPEN após `CIRCUIT_RESET_S=30`.
1. `curl http://127.0.0.1:8206/health` — qual downstream está fora.
2. `make logs` do serviço em falha; se crash loop, corrija a causa raiz.
3. Não force reset sem entender a falha — o circuito está protegendo o sistema.

## OOD false positive (query legítima bloqueada)

```bash
curl -s http://127.0.0.1:8200/v1/ood/status -H "X-Internal-Key: $KEY"   # (via exec) residual + threshold
```
Se o corpus derivou, refit com golden atualizado (`POST /v1/ood/fit`, op de admin) e
monitore o AUC. Não ajuste o golden só para o caso passar.

## Rate limit (429)

Default de produção é `RATE_LIMIT_PER_MIN=6000` (100 req/s por IP). 429 sob carga real
é raro; se surgir em teste, é o esperado (ver `make loadtest`).

## Perda de dados / recovery

```bash
make restore                        # restaura o backup mais recente
make restore DIR=backups/<ts>       # backup específico
make dr-test                        # valida o ciclo backup->perda->restore
```
Só o Qdrant tem estado de negócio. RTO medido: sub-segundo. Ver `NEXT_PHASES §15.4`.
