# svc-observability

Agregação de observabilidade do ecossistema como API stateless: **raspa** o `/metrics` de cada serviço (fonte `live`), **ingere** resultados de eval (fonte `eval`, com data), **computa** derivados (fonte `estimate`), e expõe visão unificada + **exposição Prometheus**. Cada métrica declara a **fonte** — a lição central da rodada 2026-07-04 do AI-Orchestrator (`metrics.py`, `eval_results.py`).

Sexto serviço do programa SDD (`../SDD/`). Contrato: `api/openapi.yaml`. **Não** é o Collector OTLP (isso é infra) — é a camada de agregação.

## Gates (medidos)

| Gate | Métrica | Resultado | Threshold | Baseline AIO |
|------|---------|-----------|-----------|--------------|
| G1 | Testes | **55 pass** | 100%, ≥50 | — |
| G2 | Agregação | **8/8** (parcial + stale sob falha) | 0 divergência | MetricsCollector |
| G3 | Fonte + armadilha | **6/6** (projeção = estimate, não live) | 0 divergência | fontes live/eval/estimate |
| G4 | Exposição Prometheus | **7/7** (texto reparseável) | 0 malformado | fan-out Prometheus |
| G5 | Lint+tipos | **ruff+mypy limpos** | 0 erros | — |
| G6 | Contrato | **OpenAPI válido** | 0 violações | — |
| G7 | Security | **fail-closed + SSRF OK** | ver tests | auditoria 0 |
| G8 | Perf (overview) | **P95 1.83 ms** | <40 ms | — |

## Como rodar

```bash
make venv          # cria .venv + deps (leves, sem modelo)
make gates         # G1–G8 (todos rápidos, offline via FakeScraper)
INTERNAL_KEY=k ALLOW_LOCAL_UPSTREAM=1 make run   # sobe API em :8205

INTERNAL_KEY=k UPSTREAM_KEY=<key-dos-servicos> docker compose up --build
```

## Uso

```bash
# raspar todos os upstreams agora
curl -s -X POST localhost:8205/v1/refresh -H 'X-Internal-Key: k'

# visão unificada (cada métrica com source)
curl -s localhost:8205/v1/overview -H 'X-Internal-Key: k'
# -> {"metrics":[{"name":"routes_total","value":9,"source":"live","service":"svc-router"}, ...
#     {"name":"ecosystem_tokens_total","value":150,"source":"estimate","service":"ecosystem"}]}

# ingerir resultado de eval (source=eval, com data)
curl -s -X POST localhost:8205/v1/eval-results -H 'X-Internal-Key: k' \
  -H 'content-type: application/json' \
  -d '{"service":"svc-evals","dataset_date":"2026-07-04","metrics":[{"name":"faithfulness","value":0.975}]}'

# exposição Prometheus (para scraping externo)
curl -s localhost:8205/v1/prometheus -H 'X-Internal-Key: k'
```

## Regra de fonte (inegociável)

- Raspado de `/metrics` upstream → `source=live`.
- Ingerido via `/v1/eval-results` → `source=eval` (carrega `dataset_date`).
- Computado por fórmula/projeção → `source=estimate`. **Nunca** projeção como `live` — reproduz o fix do dashboard do AIO.

## Contrato

- `GET /v1/overview` — snapshot unificado (métricas com `source`, `stale`)
- `GET /v1/services` — upstreams + status do último scrape
- `POST /v1/refresh` — raspa todos agora
- `POST /v1/eval-results` — ingere métricas de eval
- `GET /v1/prometheus` — exposição em texto Prometheus
- `GET /health` (upstreams up/total) · `GET /metrics` (`source: live`)

## Notas

- **Scraper adapter**: `HttpScraper` (prod, raspa `/metrics` com `UPSTREAM_KEY`) + `FakeScraper` (gates, offline).
- **Degradação**: upstream fora não derruba o overview — serviço `ok=false`, métricas antigas mantidas com `stale=true` (padrão MetricsCollector do AIO).
- **Não é o Collector OTLP** (§3 não-objetivo): agrega `/metrics`, não recebe OTLP.
- Auth fail-closed, anti-SSRF nas URLs de upstream, Swagger off. Decisões: `DECISIONS.md`.
