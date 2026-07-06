# ARCHITECTURE — Ecossistema de Microsserviços (derivado do AI-Orchestrator)

Mapa dos 7 serviços, contratos transversais e ordem de construção. Integração é **contract-first**: serviços conversam por API versionada; zero código compartilhado entre repos.

## 1. Os 7 serviços

| Serviço | Capacidade | Origem no AIO | Baseline medido |
|---------|-----------|---------------|-----------------|
| `svc-guardrails` **(piloto)** | Injection defense, OOD guard, sanitização, rate-limit, decisão fail-closed | `gateway/security.py`, `gateway/subspace_guard.py`, sanitize node | 0/6 injection; OOD AUC 0.9803 (LOO, thr 0.48); auditoria 0 CRIT/ALTO/MEDIO |
| `svc-router` | Roteamento 3 camadas (semântico/LLM/lexical), híbrido BM25+RRF, guards determinísticos | `gateway/router.py`, `semantic_router.py`, `bm25.py` | 94.1% no golden 153; RoutePlan.layer |
| `svc-rag` | Ingestão/chunking, busca densa (Qdrant), search_documents, GraphRAG/comunidades | `document_search.py`, `ingest_documents.py`, `community_summaries.py` | Recall@3 100% (12/12); Louvain modularity 0.618 |
| `svc-inference` | Serving LLM local (Ollama/LoRA), model mgmt, tuning | Modelfile, docker-compose ollama | 9B Q4_K_M 5.4 GB; NUM_PARALLEL=3 + FLASH_ATTN −16% makespan |
| `svc-orchestrator` | Grafo fan-out/fan-in, HITL write-intent, SSE streaming, circuit breaker, checkpointing | `graph.py`, `write_intent.py`, `tools/circuit.py` | fan-out 3 domínios 19.5 s; 410 testes |
| `svc-observability` | Coleta OTel GenAI, agregação de métricas com fonte, dashboards | `otel.py`, `metrics.py`, `otel-collector-config.yaml` | tokens na fonte; fan-out Phoenix/Prometheus |
| `svc-evals` | Golden sets, gates, juiz LLM local, relatórios, CI gate | `evals/*`, `eval_results.py` | Faithfulness 97.5%; fontes live/eval/estimate |

## 2. Mapa de dependências (runtime)

```
                          ┌──────────────────┐
  cliente ──▶ svc-orchestrator ──▶ svc-router ──▶ svc-inference (LLM)
                  │                    │
                  │                    └──▶ svc-guardrails (pré-rota: sanitize/injection/OOD)
                  ├──▶ svc-rag ──▶ Qdrant / Neo4j
                  ├──▶ serviços de domínio (por projeto — fora deste ecossistema)
                  └──▶ svc-inference (síntese)

  todos ──emitem OTLP──▶ svc-observability ──▶ Phoenix / Prometheus
  svc-evals ──consome──▶ APIs de todos (golden runs) + publica resultados p/ svc-observability
```

Regra: **dependência é sempre opcional em runtime** — dependência fora do ar = degradação declarada na spec (no-op, cache stale ou erro limpo), nunca crash em cascata. Circuit breaker no chamador (padrão AIO: 3 falhas → OPEN 30 s → half-open; 4xx não conta).

## 3. Contratos transversais (obrigatórios em TODOS os serviços)

### 3.1 Auth
- **Interna (serviço↔serviço):** header `X-Internal-Key`, comparação `hmac.compare_digest`, 401 sem a chave. Chave por ambiente via env.
- **Pública (quando exposta):** `ACCESS_TOKEN` fail-closed; modo aberto exige `ALLOW_OPEN_ACCESS=1` explícito.
- **Rate-limit:** por IP real — cadeia `CF-Connecting-IP` → `X-Real-IP` → `X-Forwarded-For` → socket; sliding window com `max_entries` + eviction (anti memory-exhaustion).

### 3.2 Saúde e ciclo de vida
- `GET /health` → `{status, version, deps: {<dep>: ok|degraded|down}}`. Sem auth (liveness de orquestrador).
- Shutdown graceful; request deadline global independente de timeouts de dependência.

### 3.3 Observabilidade
- OTLP HTTP → Collector central; chamadas LLM seguem **GenAI semconv** (`gen_ai.*` spans; histogramas token.usage / operation.duration / time_to_first_token).
- Log JSON estruturado; `trace_id` propagado via `traceparent` (W3C) entre serviços.
- `GET /metrics` (auth interna): toda métrica com campo `source: live|eval|estimate`.
- Telemetria fora do ar → no-op. Serviço nunca falha por observabilidade.

### 3.4 Contrato de API e versionamento
- OpenAPI 3.1 em `api/openapi.yaml`, versionado no repo; rotas prefixadas `/v1/`.
- SemVer: breaking → MAJOR (nova rota `/v2/`, `/v1/` mantida 1 ciclo); aditivo → MINOR.
- Erro de negócio: `422 {error, detail, rule}`. Erro interno: `500` genérico, stack só em log.

### 3.5 Repositório padrão
```
svc-<nome>/
  api/openapi.yaml        # fonte da verdade do contrato
  src/                    # FastAPI + Pydantic v2
  tests/                  # unit + contrato (sem infra externa)
  evals/                  # goldens + gates + results/
  Dockerfile  compose.yaml  pyproject.toml
  README.md  DECISIONS.md  BACKLOG.md  SPEC.md (cópia congelada da spec)
```
Stack padrão: Python 3.12, FastAPI, Pydantic v2, pytest, ruff, mypy. Desvio = justificativa em `DECISIONS.md`.

## 4. Ordem de construção

| Rodada | Serviço | Racional |
|--------|---------|----------|
| 1 | `svc-guardrails` | Piloto: menor superfície, zero deps de infra nos gates, baselines prontos → calibra template + loop |
| 2 | `svc-evals` | Passa a validar os demais; gates dos próximos serviços rodam via ele |
| 3 | `svc-inference` | Base LLM para router/orchestrator/rag |
| 4 | `svc-router` | Depende de inference (camada LLM) + guardrails |
| 5 | `svc-rag` | Depende de inference (embeddings/resumos) |
| 6 | `svc-observability` | Consolida telemetria já emitida pelos anteriores |
| 7 | `svc-orchestrator` | Integra tudo — último de propósito: é o teste de integração do ecossistema |

**Gate entre rodadas:** serviço anterior DONE (todos os gates PASS) + retrospectiva registrada em `SDD/RETRO.md` + template atualizado se necessário.
