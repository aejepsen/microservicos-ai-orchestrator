# Arquitetura — AI-Orchestrator Microsserviços

Ecossistema de 7 microsserviços FastAPI derivados do AI-Orchestrator, contract-first
(zero código compartilhado), integrados por OpenAPI `/v1/` + padrões transversais
(auth `X-Internal-Key`, `/health`, `/metrics`, OTel W3C).

> Este documento descreve o **as-built** do stack single-node (`docker-compose.prod.yml`).
> A topologia Kubernetes do roadmap (Fase 11) foi **skipped** — o caso de uso é
> single-node com GPU local. Ver `SDD/NEXT_PHASES.md §12.4`.

## Fluxo de um `/v1/chat`

```
                        cliente (127.0.0.1)
                              │  POST /v1/chat  (X-Internal-Key)
                              ▼
                   ┌──────────────────────┐
                   │  svc-orchestrator     │  :8206  (grafo fan-out/fan-in, HITL, SSE)
                   └──────────┬───────────┘
          ┌──────────────────┼───────────────────────────┐
          ▼                  ▼                            ▼
   ┌────────────┐     ┌────────────┐              ┌────────────┐
   │ guardrails │     │  router    │              │   rag      │  (por domínio roteado)
   │  :8200     │     │  :8203     │              │  :8204     │
   │ injection  │     │ 3 camadas: │              │ ingest +   │
   │ + OOD +    │     │ SBERT+BM25 │              │ search +   │
   │ sanitize   │     │ +LLM fallb.│              │ GraphRAG   │
   └────────────┘     └─────┬──────┘              └─────┬──────┘
                            │ fallback LLM              │ vetores
                            ▼                           ▼
                     ┌────────────┐              ┌────────────┐
                     │ inference  │◄─────────────│   Qdrant   │  :6333 (rede interna)
                     │  :8202     │  geração     └────────────┘
                     │ OpenAI-cmp │
                     └─────┬──────┘
                           ▼
                     ┌────────────┐
                     │   Ollama   │  :11434 (rede interna, GPU RTX 3060)
                     │ qwen3.5-9b │
                     └────────────┘

svc-observability :8205  — raspa /metrics dos 6 serviços + orchestrator (pull)
svc-evals         :8201  — motor de avaliação por golden-set (offline/admin)

Observabilidade:  Jaeger :16686 (traces)  ·  Prometheus :9090  ·  Grafana :3000
```

## Portas (todas publicadas só em 127.0.0.1)

| Serviço | Porta | Exposto ao host | Papel |
|---------|-------|-----------------|-------|
| svc-orchestrator | 8206 | ✅ entrada pública | grafo, HITL, SSE |
| svc-rag | 8204 | ✅ (admin: ingest) | recuperação |
| svc-observability | 8205 | ✅ | agregação de métricas |
| svc-guardrails | 8200 | rede interna | injection + OOD |
| svc-evals | 8201 | rede interna | avaliação |
| svc-inference | 8202 | rede interna | fachada LLM |
| svc-router | 8203 | rede interna | roteamento |
| Qdrant | 6333 | **rede interna** (backend `internal`) | vetores |
| Ollama | 11434 | **rede interna** | LLM na GPU |
| Jaeger | 16686 | ✅ UI | traces |
| Prometheus | 9090 | ✅ | métricas TSDB |
| Grafana | 3000 | ✅ UI | dashboards |

## Redes

- **`backend`** (`internal: true`): Qdrant, Ollama e o tráfego inter-serviços. Sem
  rota pro host — superfície mínima.
- **`edge`**: só os serviços com porta publicada + egress do Ollama (`ollama pull`).

## Padrões transversais

- **Auth:** `X-Internal-Key` em toda rota `/v1/`, `hmac.compare_digest` (timing-safe), fail-closed (401 sem chave).
- **Health:** `GET /health` (sem auth) agrega dependências.
- **Métricas:** `GET /metrics` (auth) JSON; o svc-observability converte pra formato Prometheus em `/v1/prometheus`.
- **Traces:** OTel OTLP → Jaeger, propagação W3C `traceparent` ponta a ponta.
- **Segurança:** containers non-root (`appuser`), `cap_drop: ALL`, `no-new-privileges`, security headers, `max_length` nos inputs. Ver `docs/RUNBOOK.md` e `SDD/NEXT_PHASES.md §13.3`.

## Estado persistente

Só o **Qdrant** guarda dado insubstituível (vetores RAG). Grafana/Prometheus são
recuperáveis (provisioning em git / métricas lossy-ok); serviços são stateless.
Backup/restore: `make backup|restore|dr-test` (§15.4).
