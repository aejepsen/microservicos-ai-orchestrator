# svc-router

Roteamento de intenção em **3 camadas** como API stateless: (1) **semântica híbrida** (denso SBERT + BM25 fundidos por RRF), (2) **guards léxicos determinísticos**, (3) **fallback LLM** (adapter OpenAI-compat opcional). Devolve um **RoutePlan** rastreável (`domains`, `layer`, `scores`). Extraído de `router.py`/`semantic_router.py`/`bm25.py` do AI-Orchestrator.

Quarto serviço do programa SDD (`../SDD/`) — primeiro a consumir outros do ecossistema (`svc-inference` na camada LLM). Contrato: `api/openapi.yaml`.

## Gates (medidos)

| Gate | Métrica | Resultado | Threshold | Baseline AIO |
|------|---------|-----------|-----------|--------------|
| G1 | Testes | **55 pass** | 100%, ≥50 | — |
| G2 | Acurácia roteamento (SBERT) | **0.967** (29/30) | ≥0.85 | 94.1% (golden 153) |
| G3 | Fusão RRF + camadas | **5/5** (RRF à mão) | 0 divergência | RRF do AIO |
| G4 | Guards + armadilha | **6/6** (armadilha não dispara) | ver dogfood | — |
| G5 | Lint+tipos | **ruff+mypy limpos** | 0 erros | — |
| G6 | Contrato | **OpenAPI válido** | 0 violações | — |
| G7 | Security | **fail-closed + SSRF OK** | ver tests | auditoria 0 |
| G8 | Perf (overhead) | **P95 0.17 ms** | <60 ms (FakeEmbedder) | — |

## Como rodar

```bash
make venv          # cria .venv + deps (inclui SBERT via torch)
make gates         # G1–G8 (G2 carrega SBERT; demais offline)
INTERNAL_KEY=k make run   # sobe API em :8203

INTERNAL_KEY=k docker compose up --build
```

## Uso

```bash
curl -s localhost:8203/v1/route -H 'X-Internal-Key: k' \
  -H 'content-type: application/json' \
  -d '{"query":"Qual a comissão do vendedor 12?"}'
# -> {"domains":["vendas","financas"],"layer":"lexical","scores":{...},"llm_used":false}

# rotas inline (override das registradas)
curl -s localhost:8203/v1/route -H 'X-Internal-Key: k' \
  -H 'content-type: application/json' \
  -d '{"query":"alpha","routes_override":[{"name":"x","exemplars":["alpha um"]},{"name":"y","exemplars":["beta"]}]}'
```

## Camadas de decisão

1. **Semântica híbrida**: embed da query vs. exemplares; denso + BM25 fundidos por RRF; se `top_cosseno ≥ ROUTE_THRESHOLD` → `layer=semantic` (+ empates dentro de `TIE_MARGIN` = multi-domínio).
2. **Guards léxicos**: sempre aplicados; **adicionam** domínios (ex.: "comissão" → vendas+finanças). Se decidem sem semântica → `layer=lexical`.
3. **Fallback LLM**: semântica < threshold e sem guard → classifica via `svc-inference`; `layer=llm`. Adapter fora → 503 (ou `layer=fallback` semântico se `LLM_FALLBACK_SOFT=1`).

## Contrato

- `POST /v1/route` — query → RoutePlan (`domains`, `layer`, `scores`, `llm_used`)
- `GET /v1/routes` — rotas registradas
- `GET /health` (deps: embedder, llm_adapter) · `GET /metrics` (`by_layer`, `source: live`)

## Notas

- **Stateless**; embeddings dos exemplares no boot (SBERT). Embedder fora → semântica off, guards+LLM seguem, `/health` degraded.
- Camada LLM é adapter (`svc-inference`); gates usam FakeLLM/FakeEmbedder — 100% offline.
- Auth fail-closed, anti-SSRF no `LLM_URL`, Swagger off, `.env`/`models` fora do git. Decisões: `DECISIONS.md`.
