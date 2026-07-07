# API Reference

Todos os serviços expõem o mesmo contrato transversal e endpoints `/v1/` próprios.
O contrato completo por serviço está em cada `svc-*/api/openapi.yaml` (OpenAPI 3.1).
Swagger interativo é **desabilitado** em runtime (`docs_url=None`) por segurança.

## Transversal (todos os serviços)

| Método | Rota | Auth | Descrição |
|--------|------|------|-----------|
| GET | `/health` | não | Estado + dependências. Nunca 401. |
| GET | `/metrics` | sim | Métricas JSON do serviço. |

Auth: header `X-Internal-Key: <INTERNAL_KEY>` em toda rota `/v1/` e `/metrics`.
Sem chave → 401. Chave errada → 401 (timing-safe).

## svc-orchestrator (:8206) — entrada pública

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/v1/chat` | Chat com RAG+LLM. `{"query": str, "stream"?: bool, "allow_write"?: bool}`. `stream:true` → SSE (`text/event-stream`). |
| POST | `/v1/chat/{thread_id}/resume` | Retoma thread pausada (HITL write-intent). `{"approve": bool}`. |
| GET | `/v1/threads/{thread_id}` | Estado de uma thread. |

Respostas do `/v1/chat`: `decision` (answered/blocked/paused), `domains`, `agents`
(com `context_used`), `final`, `thread_id`. Códigos: 200 ok · 403 injection · 401 auth
· 422 input inválido · 503 downstream fora.

```bash
curl -s -X POST http://127.0.0.1:8206/v1/chat \
  -H "X-Internal-Key: $INTERNAL_KEY" -H 'Content-Type: application/json' \
  -d '{"query": "Qual o faturamento total do trimestre?"}'
```

## svc-guardrails (:8200)

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/v1/analyze` | Injection + OOD + sanitização. `{"text": str, "checks"?: [str]}`. |
| POST | `/v1/ood/fit` | Refit do detector OOD (admin). Corpus + golden. |
| GET | `/v1/ood/status` | Residual, threshold, AUC. |

Limite: `text` até `MAX_TEXT_CHARS` (default 8000) → 413 se exceder.

## svc-router (:8203)

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/v1/route` | Roteia query em domínios. Retorna `{domains, layer, scores, llm_used}`. |
| GET | `/v1/routes` | Domínios/exemplares registrados. |

Camadas: semântica (SBERT+BM25/RRF) → guards léxicos → fallback LLM.

## svc-rag (:8204) — admin exposto

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/v1/ingest` | Ingesta docs. `{"collection": str, "documents": [{"id", "text"}]}`. Idempotente por hash. |
| POST | `/v1/search` | Busca semântica. `{"collection", "query", "top_k"}`. |
| GET | `/v1/collections` | Coleções existentes. |
| GET | `/v1/community/{cid}` | Comunidade GraphRAG. |

## svc-inference (:8202) — fachada OpenAI-compat

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/v1/chat/completions` | Chat completions (bloqueante ou SSE). Compatível OpenAI. |
| GET | `/v1/models` | Modelos disponíveis no backend Ollama. |

## svc-observability (:8205)

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/v1/overview` | Visão agregada do ecossistema (cache). |
| GET | `/v1/prometheus` | Métricas em formato Prometheus (texto). Raspado pelo Prometheus. |
| POST | `/v1/refresh` | Força raspagem dos upstreams. |
| GET | `/v1/services` | Serviços monitorados + estado. |

## svc-evals (:8201) — offline/admin

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/v1/run` | Roda uma suíte de avaliação. |
| GET | `/v1/suites` | Suítes disponíveis. |
| GET | `/v1/results` · `/v1/results/{suite}` | Resultados de gates/scorers. |
