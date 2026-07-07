# svc-orchestrator

Orquestração multi-agente como API independente: **sanitize → route → fan-out → fan-in** sobre os 4 downstream (svc-guardrails, svc-router, svc-rag, svc-inference), com **HITL** por write-intent (léxico PT determinístico), **SSE** de eventos ao vivo e **circuit breaker** por downstream. Extraído do grafo validado em produção do AI-Orchestrator (`graph.py`, `write_intent.py`), sem LangGraph — pipeline linear + fan-out em Python puro.

Rodada 7 do programa SDD (`../SDD/`). Contrato: `api/openapi.yaml`.

## Fluxo

```
query ──▶ guardrails (fail-closed) ──block──▶ 403/evento blocked
              │ allow/flag
              ▼
           router ──▶ [route]
              │
   HITL? write-intent + !allow_write ──▶ [paused] ──resume(approve)──┐
              │ leitura ou aprovado                                  │
              ▼                                                      ▼
        fan-out por domínio ──▶ agente = rag (opcional) + inference ──▶ [agent]×N
              │
              ▼
        fan-in: síntese (multi) ou resposta direta (single) ──▶ [final]
```

Cada downstream: circuit breaker (3 falhas de transporte → OPEN; 4xx não conta) + `traceparent` W3C propagado.

## Gates (medidos)

| Gate | Métrica | Resultado | Threshold | Baseline AIO |
|------|---------|-----------|-----------|--------------|
| G1 | Testes | **66 pass** | 100%, ≥55 | 410 (AIO todo) |
| G2 | Fluxo de orquestração | **9/9 checks** | single/multi/block corretos | fan-out graph.py |
| G3 | HITL + armadilha | **12/12 checks** | escrita pausa; "contas a pagar" não | write_intent.py |
| G4 | SSE + resiliência | **6/6 checks** | route→agent→final; guardrails fora → fail-closed | breaker 3→OPEN |
| G5 | Lint+tipos | **ruff+mypy limpos** | 0 erros | — |
| G6 | Contrato | **OpenAPI válido, 5/5 rotas testadas** | 0 violações | — |
| G7 | Security+trace | **fail-closed, SSRF, traceparent OK** | ver tests | auditoria 0 achados |
| G8 | Perf P95 (overhead) | **1.8 ms** | <50 ms (fakes, single) | — |

## Como rodar

```bash
make venv          # cria .venv + instala deps
make gates         # G1–G8 na mesma execução
make run           # sobe API em :8206 (exige INTERNAL_KEY)

# ou via Docker
INTERNAL_KEY=troque docker compose up --build

# smoke opcional contra o ecossistema real (4 downstream no ar)
SMOKE_BASE_URL=http://127.0.0.1:8206 SMOKE_INTERNAL_KEY=<key> make smoke
```

## Uso

```bash
# chat single-domínio (JSON)
curl -s localhost:8206/v1/chat -H 'X-Internal-Key: <key>' \
  -H 'content-type: application/json' \
  -d '{"query":"qual o saldo em caixa?"}'
# -> {"thread_id":"th-...","decision":"answered","domains":["financas"],"agents":[...],"final":"..."}

# chat multi-domínio streaming (SSE): eventos route -> agent (xN) -> final -> done
curl -sN localhost:8206/v1/chat -H 'X-Internal-Key: <key>' \
  -H 'content-type: application/json' \
  -d '{"query":"saldo em caixa e funcionários de férias?","stream":true}'

# HITL: escrita pausa (HITL_ENABLED=1) e retoma com aprovação
curl -s localhost:8206/v1/chat -H 'X-Internal-Key: <key>' \
  -H 'content-type: application/json' -d '{"query":"Cadastre um novo funcionário"}'
# -> {"decision":"paused","pending_write":{...},"thread_id":"th-abc"}
curl -s localhost:8206/v1/chat/th-abc/resume -H 'X-Internal-Key: <key>' \
  -H 'content-type: application/json' -d '{"approve":true}'
# -> {"decision":"answered","final":"..."}
```

## Contrato

- `POST /v1/chat` — orquestra a query; `stream=true` → `text/event-stream` (`route|agent|final|blocked|paused|error|done`)
- `POST /v1/chat/{thread_id}/resume` — retoma thread pausada por HITL (`approve: bool`)
- `GET /v1/threads/{thread_id}` — estado da thread (decision, final, pending_write)
- `GET /health` — liveness + estado dos circuit breakers por downstream
- `GET /metrics` — contadores agregados (`source: live`)

Config completa (env) em `SPEC.md` §7; downstreams e portas default no `compose.yaml`.

## Notas

- **Guardrails é fail-closed**: fora do ar → 503/erro, o fluxo NUNCA segue sem análise. RAG é opcional (fora → segue sem contexto); inference parcial marca o domínio e a síntese usa o que respondeu.
- HITL determinístico (`write_intent.py`): verbo imperativo de escrita + objeto; frase nominal ("relatório de contas a pagar") não pausa; leitura nunca pausa. Opt-in `HITL_ENABLED=1`.
- Gates rodam 100% offline (FakeClients determinísticos); nenhum gate exige serviço no ar.
- Auth fail-closed (`X-Internal-Key` + `hmac.compare_digest`); anti-SSRF nas URLs de downstream; rate-limit por IP; Swagger off; `.env` fora do git.
- Desvios e decisões: `DECISIONS.md`. Fora de escopo: `BACKLOG.md`.
