# svc-inference

Fachada de inferência LLM **OpenAI-compatível** sobre um backend local (Ollama). Chat completions (bloqueante + streaming SSE), listagem de modelos, **usage de tokens na fonte**, spans OTel GenAI, TTFT medido, circuit breaker e degradação graceful. Extraído de `gateway/llm.py` + `gateway/otel.py` + `tools/circuit.py` do AI-Orchestrator.

Terceiro serviço do programa SDD (`../SDD/`). Contrato: `api/openapi.yaml`. Não hospeda pesos — orquestra a chamada ao backend.

## Gates (medidos)

| Gate | Métrica | Resultado | Threshold | Baseline AIO |
|------|---------|-----------|-----------|--------------|
| G1 | Testes | **57 pass** | 100%, ≥50 | — |
| G2 | Compat OpenAI | **10/10** (bloqueante + stream + [DONE]) | 0 divergência | — |
| G3 | Tokens na fonte | **7/7** (usage → resposta e /metrics) | nunca estimado | fix tokens=0 do AIO |
| G4 | Resiliência | **5/5** (circuito abre; 4xx não abre) | ver dogfood | breaker 3→OPEN 30s |
| G5 | Lint+tipos | **ruff+mypy limpos** | 0 erros | — |
| G6 | Contrato | **OpenAPI válido** | 0 violações | — |
| G7 | Security | **fail-closed OK** | ver tests | auditoria 0 |
| G8 | Perf (overhead) | **P95 1.9 ms** | <30 ms (FakeBackend) | — |

## Como rodar

```bash
make venv          # cria .venv + deps (leves, sem modelo)
make gates         # G1–G8 na mesma execução (BACKEND=fake, offline)
BACKEND=fake INTERNAL_KEY=k make run   # sobe API em :8202
make smoke         # opcional: exige Ollama real no ar (BACKEND=ollama)

INTERNAL_KEY=k BACKEND=ollama docker compose up --build
```

## Uso

```bash
# chat bloqueante (OpenAI-compat)
curl -s localhost:8202/v1/chat/completions -H 'X-Internal-Key: k' \
  -H 'content-type: application/json' \
  -d '{"model":"qwen3.5-9b-orch","messages":[{"role":"user","content":"Olá"}]}'
# -> {"object":"chat.completion","choices":[...],"usage":{"prompt_tokens":...}}

# streaming SSE
curl -N localhost:8202/v1/chat/completions -H 'X-Internal-Key: k' \
  -H 'content-type: application/json' \
  -d '{"model":"qwen3.5-9b-orch","stream":true,"messages":[{"role":"user","content":"Olá"}]}'
# -> data: {chunk}\n\n ... data: {usage no último}\n\n data: [DONE]

curl -s localhost:8202/v1/models -H 'X-Internal-Key: k'
```

## Contrato

- `POST /v1/chat/completions` — completion; `stream:true` → SSE de chunks + `[DONE]`; usage no último chunk
- `GET /v1/models` — modelos do backend (formato OpenAI)
- `GET /health` · `GET /metrics` (tokens, TTFT, latências, circuit_state; `source: live`)

## Backends

- `BACKEND=ollama` (default): HTTP para Ollama; usage na fonte (`prompt_eval_count`/`eval_count`).
- `BACKEND=fake`: determinístico, para dev/gates — **zero rede**.
- Trocar Ollama por vLLM/TGI no futuro = novo adapter; o contrato OpenAI não muda para os consumidores.

## Notas

- **Circuit breaker** (padrão AIO): 3 falhas de transporte → OPEN 30s → half-open; **4xx não abre o circuito**.
- **Deadline** por request → 504; backend fora → 503 limpo; nunca crash.
- **OTel GenAI** opt-in (`OTEL_ENABLED=1`): spans `gen_ai.*` + histogramas token.usage/duration/TTFT; no-op se off.
- Tuning de hardware (NUM_PARALLEL, FLASH_ATTENTION) é do backend/AIO — documentado, não re-medido aqui.
- Auth fail-closed, Swagger off, `.env` fora do git. Decisões: `DECISIONS.md`.
