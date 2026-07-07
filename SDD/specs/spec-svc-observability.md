# SPEC — svc-observability v1.0

> Sexta spec do programa SDD (rodada 6). Derivada de `../SPEC_TEMPLATE.md` calibrado por RETRO rodadas 1–5. Contrato único entre arquiteto e loop de agentes.

---

## 0. Metadados

| Campo | Valor |
|-------|-------|
| Serviço | `svc-observability` |
| Versão da spec | 1.0.0 |
| Status | **frozen** |
| Baseline de referência | AI-Orchestrator `fe3adc1` — `gateway/metrics.py` (MetricsCollector, cache, scrape do Prometheus), `gateway/eval_results.py` (fontes live/eval/estimate), `otel-collector-config.yaml` (fan-out Phoenix/Prometheus) |
| Repo alvo | `~/Documentos/projeto-portifolio/microservicos-ai-orchestrator/svc-observability` |
| Data de congelamento | 2026-07-06 |

## 1. Contexto e problema

Cada serviço do ecossistema expõe `/metrics` com contadores próprios e o campo **`source: live`**. Falta uma camada que **consolide** essa telemetria numa visão única, some contadores comparáveis, e distinga a **fonte** de cada número — a lição central da rodada 2026-07-04 do AIO: toda métrica de dashboard declara se é `live` (traces/contadores reais), `eval` (golden set, com data) ou `estimate` (fórmula). O AIO fazia isso no `eval_results.py` + `metrics.py` (que também raspava o Prometheus do Collector como fonte independente do Langfuse).

Este serviço extrai a **agregação de observabilidade** para uma API independente: registra os serviços upstream, **raspa** o `/metrics` de cada um (fonte `live`), **ingere** resultados de eval (fonte `eval`, ex.: do svc-evals), **computa** derivados documentados (fonte `estimate`), e expõe (a) `/v1/overview` — snapshot unificado com fonte por métrica; (b) `/v1/prometheus` — exposição em texto Prometheus para scraping externo (reproduz o fan-out). Consumidores: um dashboard (fora deste escopo), Prometheus/Grafana, e o operador.

Padrão herdado (template §8.5): o **scraper de upstream é adapter + fake** — gates usam `FakeScraper` determinístico, sem serviço no ar. O Collector OTLP (Phoenix/Prometheus) é **infra**, não este serviço — svc-observability é a camada de agregação, não o receptor OTLP.

Lição institucionalizada: o golden de fontes carrega **armadilha** — uma métrica que parece `live` mas é `estimate` (projeção) deve ser rotulada `estimate`, nunca `live` (§12.7).

## 2. Objetivo (uma frase)

Consolidar a telemetria dos serviços do ecossistema numa visão única com **fonte por métrica** (`live`/`eval`/`estimate`), raspando `/metrics` upstream, ingerindo resultados de eval e computando derivados, com exposição Prometheus, testável 100% offline via scraper fake.

## 3. Não-objetivos (o agente NÃO constrói)

- Ser o Collector OTLP / receber OTLP dos serviços — isso é infra (`otel-collector-config.yaml`), não este serviço.
- Dashboard / UI / gráficos — svc-observability serve os dados; a visualização é outro componente.
- Alerting / paging — sem regras de alerta nesta versão (BACKLOG).
- Armazenamento de séries temporais de longo prazo (TSDB) — snapshot + cache curto; histórico rico → BACKLOG.
- Tracing distribuído / correlação de spans — os spans vão pro Phoenix via Collector; aqui é agregação de métricas.
- Autenticar/rotear tráfego dos serviços — não é gateway.
- Gerar os resultados de eval — apenas **ingere** o que o svc-evals produz.

## 4. Glossário

| Termo | Definição neste contexto |
|-------|--------------------------|
| Upstream | Serviço do ecossistema cujo `/metrics` é raspado |
| Scrape | Buscar `/metrics` de um upstream e normalizar |
| Métrica normalizada | `{name, value, source, service, unit?, ts}` |
| Fonte (`source`) | `live` (raspado/contador real) \| `eval` (golden, com data) \| `estimate` (fórmula/projeção) |
| Overview | Snapshot unificado de todas as métricas, agrupado por serviço/nome |
| Exposição Prometheus | Texto no formato Prometheus (`# HELP`, `# TYPE`, `name{labels} value`) |
| Derivado | Métrica computada a partir de outras (ex.: total de tokens do ecossistema) — sempre `estimate` se projeção |
| Armadilha | Métrica projetada rotulada por engano como `live` (deve ser `estimate`) |

## 5. Contrato de API

> Fonte da verdade: `api/openapi.yaml` (OpenAPI 3.1), gerado na F1, validado com `openapi-spec-validator`. Rotas `/v1/`.

### 5.1 Endpoints

| Método | Rota | Auth | Descrição | Erros |
|--------|------|------|-----------|-------|
| GET | `/v1/overview` | interna | Snapshot unificado; cada métrica com `source`; cache curto | 401 |
| GET | `/v1/services` | interna | Upstreams registrados + status do último scrape | 401 |
| POST | `/v1/refresh` | interna | Força scrape de todos os upstreams agora | 401 |
| POST | `/v1/eval-results` | interna | Ingere métricas de eval (fonte `eval`, com data) | 401, 422 |
| GET | `/v1/prometheus` | interna | Exposição em texto Prometheus de todas as métricas | 401 |
| GET | `/health` | nenhuma | Liveness + readiness (deps: upstreams alcançáveis) | — |
| GET | `/metrics` | interna | Métricas do próprio serviço (`source: live`) | 401 |

### 5.2 Schemas principais (Pydantic v2 espelha o OpenAPI)

```yaml
Metric: {name: str, value: number, source: "live"|"eval"|"estimate", service: str, unit?: str, ts?: str}
Overview: {metrics: list[Metric], generated_at: str}
ServiceStatus: {name: str, url: str, last_scrape: str|null, ok: bool, n_metrics: int}
EvalResultIn: {service: str, metrics: list[{name, value, unit?}], dataset_date: str}  # vira source=eval
EvalResultResponse: {ingested: int}

Erro de negócio: 422 {error, detail, rule}
Erro interno: 500 genérico — stack só em log.
```

### 5.3 Regra de fonte (inegociável)
- Raspado de `/metrics` upstream → `source=live`.
- Ingerido via `/v1/eval-results` → `source=eval` (carrega `dataset_date`).
- Computado por fórmula/projeção → `source=estimate`. **Nunca** rotular projeção como `live`. (Espelha o fix do dashboard do AIO.)

### 5.4 Contrato de erro
- Negócio: `422 {error, detail, rule}`. Upstream fora no scrape **não** derruba `/v1/overview` — marca o serviço `ok=false` e segue (degradação).
- Interno: `500` genérico; stack só em log.

## 6. Modelo de dados e estado

- **Estado de processo**: registro de upstreams (nome+url), cache do último scrape por serviço (com TTL), store em memória dos resultados de eval ingeridos. Sem banco (histórico longo é BACKLOG).
- **Upstreams** definidos em código/config (`src/obs_svc/upstreams.py`): os serviços do ecossistema com seus `/metrics`. Registro dinâmico opcional fica no BACKLOG (v1 = config).
- Isolamento de artefatos (template §6): N/A — sem artefatos de eval-script servidos por API; o store de eval-results é em memória.

## 7. Configuração (env — 12-factor)

| Variável | Default | Obrigatória | Efeito |
|----------|---------|-------------|--------|
| `INTERNAL_KEY` | — | sim (prod) | Auth interna (deste serviço); ausente → 401 (fail-closed) |
| `ALLOW_OPEN_ACCESS` | `0` | não | `1` libera sem key (dev; warning no boot) |
| `UPSTREAM_KEY` | — | não | Chave usada para raspar o `/metrics` dos upstreams (X-Internal-Key deles) |
| `SCRAPE_TIMEOUT_S` | `5` | não | Timeout por scrape de upstream |
| `OVERVIEW_CACHE_TTL_S` | `10` | não | TTL do cache de `/v1/overview` |
| `SCRAPE_INTERVAL_S` | `0` | não | `>0` liga scrape periódico em background; `0` = só sob demanda (`/v1/refresh`) |
| `ALLOW_LOCAL_UPSTREAM` | `0` | não | `1` permite upstream em loopback/rede interna (dev) |
| `RATE_LIMIT_PER_MIN` | `120` | não | Sliding window por IP |
| `OTEL_ENABLED` | `0` | não | OTLP → Collector; fora = no-op |
| `LOG_LEVEL` | `INFO` | não | Log JSON estruturado |

> Fail-closed na auth; degradação graceful no scrape (upstream fora não derruba o overview).

## 8. NFRs

### 8.1 Segurança
- Transversais (ARCHITECTURE §3.1): `hmac.compare_digest`, fail-closed, Swagger off, `.dockerignore`, `.env` fora do git.
- **URLs de upstream** vêm de config do operador; validar esquema http/https + bloquear metadata/loopback (anti-SSRF) salvo `ALLOW_LOCAL_UPSTREAM=1` (em dev os upstreams são localhost — daí o opt-in).
- Payload de `/v1/eval-results` é dado não confiável: validar tipos; nunca `eval`; nunca ecoar em erro sem escape.

### 8.2 Performance
- `/v1/overview` (cache quente): **P95 < 40 ms**.
- Scrape de upstream: latência da rede — medida e reportada, não gateada.

### 8.3 Observabilidade
- O próprio serviço expõe `/metrics` (`scrapes_total`, `overviews_total`, `upstreams_up`, latências) com `source: live`.
- Log JSON por operação com `trace_id`.
- Toda métrica servida em `/v1/overview` e `/v1/prometheus` **declara a fonte** — é a razão de ser do serviço.

### 8.4 Resiliência
- Upstream fora no scrape → serviço marcado `ok=false`, métricas antigas (se em cache) mantidas com flag `stale`, overview segue. Nunca crash.
- Cache stale melhor que zero observabilidade (padrão MetricsCollector do AIO).
- Deadline por request; scrape periódico (se ligado) não bloqueia requests.

## 9. Dependências

| Dependência | Tipo | Runtime obrigatória? | Se ausente |
|-------------|------|----------------------|------------|
| Serviços upstream (`/metrics`) | serviço | não (scraper fake nos gates) | serviço `ok=false`; overview parcial |
| OTel Collector | infra | não | no-op |
| **Nenhum banco, nenhum modelo** | — | — | — |

> Gates rodam 100% offline com `FakeScraper` (payloads de `/metrics` sintéticos). Nenhum gate exige upstream no ar.

## 10. Gates de aceitação

> Velocidade: todos **rápidos** (sem modelo, sem rede). `make gates` roda todos na mesma execução.

| # | Gate | Velocidade | Comando | Threshold | Baseline AIO |
|---|------|-----------|---------|-----------|--------------|
| G1 | Testes | rápido | `python -m pytest -q` | 100% pass, ≥ 50 testes | — |
| G2 | Agregação | rápido | `python evals/eval_aggregation.py` | overview funde upstreams certo; contadores somados; serviço fora → parcial + stale | MetricsCollector |
| G3 | Rótulo de fonte + armadilha | rápido | `python evals/eval_source.py` | live/eval/estimate corretos; **projeção rotulada estimate, não live**; eval carrega dataset_date | fontes live/eval/estimate |
| G4 | Exposição Prometheus | rápido | `python evals/eval_prometheus.py` | texto parseável: `# HELP`/`# TYPE`/linhas `name{labels} value`; 0 malformado | fan-out Prometheus :8889 |
| G5 | Lint + tipos | rápido | `ruff check . && python -m mypy src/` | 0 erros | — |
| G6 | Contrato | rápido | `openapi-spec-validator api/openapi.yaml && python -m pytest tests/test_contract.py` | 0 violações; toda rota testada | — |
| G7 | Security | rápido | `python -m pytest tests/test_security.py` | fail-closed, 401, SSRF do upstream, stack não vaza | auditoria 0 |
| G8 | Perf | rápido | `python evals/bench_latency.py` | `/v1/overview` P95 < 40 ms (cache) | — |

**Dogfood (o agente constrói em F2–F4):**
- *FakeScraper determinístico*: dado um serviço, devolve um payload de `/metrics` fixo (contadores + latências) — sem rede.
- *eval_aggregation*: 3 upstreams fake → overview soma/mescla; 1 fora → parcial + `ok=false` + `stale`.
- *eval_source*: métricas de cada fonte; **armadilha** = derivado de projeção que NÃO pode virar `live`.
- *eval_prometheus*: reparse do texto gerado valida formato (HELP/TYPE/linhas), labels `service`/`source`.

## 11. Plano de fases

| Fase | Entregável | Verificação | Stop condition |
|------|-----------|-------------|----------------|
| F0 | Scaffold robusto (template §11): repo no destino, todos os dirs de uma vez, pyproject, Dockerfile, Makefile (`python -m`), CI, SPEC.md | `docker build .` + `make check` + `.venv/bin/python` existe | build verde |
| F1 | `api/openapi.yaml` + schemas Pydantic (Metric/Overview/EvalResultIn) | G6 | contrato validado |
| F2 | Modelo de métrica + scraper (Fake+Http) + agregador + testes | G1 subset + G2 + G5 | agregação correta |
| F3 | Rótulo de fonte + ingest de eval-results + derivados + `eval_source.py` | G3 | fontes corretas + armadilha |
| F4 | Exposição Prometheus + `eval_prometheus.py` | G4 | formato válido |
| F5 | API completa (`/v1/overview`, `/v1/services`, `/v1/refresh`, `/v1/eval-results`) + auth + SSRF + rate-limit | G6 + G7 | security PASS |
| F6 | `/health` + `/metrics` + scrape periódico opt-in + cache stale + logs | smoke via compose | telemetria ok |
| F7 | Bench + README (gates medidos) + DECISIONS.md | **G1–G8 todos na mesma execução** | **DONE** |

## 12. Regras para o agente

1. Escopo = esta spec. Fora → `BACKLOG.md`.
2. Contradição/gate impossível → PARAR e perguntar.
3. Mesmo gate falhando após 3 correções distintas → parar, diagnóstico em `DECISIONS.md`.
4. Commits convencionais, ≥ 1 por fase. Nunca commitar `.env`, artefatos.
5. Só reportar números medidos pelos comandos da §10.
6. Dependência nova fora do pyproject inicial (fastapi, uvicorn, pydantic, httpx, pytest, ruff, mypy, openapi-spec-validator, pyyaml) → justificar em `DECISIONS.md`. **Não** adicionar cliente Prometheus pesado; formato de texto é simples o suficiente para gerar à mão.
7. **Fonte é inegociável (§5.3) e o golden tem armadilha** (§12.7): projeção nunca é `live`.
8. Scraper via adapter + FakeScraper; nenhum gate exige upstream no ar.
9. Teste de SSRF-permitido usa **IP literal público** (template §8.5), não hostname.
10. **Não tocar:** nada fora deste repo. Não implementar o Collector OTLP (é infra).

## 13. Riscos

| Risco | Prob. | Impacto | Mitigação |
|-------|-------|---------|-----------|
| Métrica projetada rotulada `live` por engano | M | A | §5.3 + armadilha no G3; derivados nascem `estimate` por construção |
| Formato Prometheus malformado (label/escape) | M | M | G4 reparseia o texto; escape de labels testado |
| Upstream fora derruba o overview | M | A | Try/except por serviço; `ok=false` + cache stale; G2 cobre |
| SSRF via URL de upstream | B | A | Validação de esquema + bloqueio metadata/loopback (opt-in dev); G7 |
| Confundir-se com o Collector OTLP | B | M | §3 não-objetivo explícito; svc-observability agrega, não recebe OTLP |

## 14. Definição de DONE

- [ ] G1–G8 PASS na mesma execução; log em `evals/results/`
- [ ] `docker compose up` + smoke (`/v1/refresh` + `/v1/overview` com FakeScraper → métricas com fonte)
- [ ] README: como rodar/testar, tabela de gates com números medidos, exemplo de overview + prometheus
- [ ] `DECISIONS.md` com desvios; `BACKLOG.md` (alerting, TSDB, registro dinâmico)
- [ ] Zero secrets/artefatos no git
- [ ] Entrada em `../RETRO.md` (rodada 6): padrões do template bastaram? novas fricções?
