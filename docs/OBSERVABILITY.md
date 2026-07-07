# Observability SOP — debugging via traces e métricas

Procedimento operacional para investigar o comportamento do stack usando as três
fontes: **Jaeger** (traces, latência por hop), **Prometheus** (métricas, PromQL) e
**Grafana** (dashboards). Complementa `docs/RUNBOOK.md` (que é sintoma→fix); aqui é
**como usar as ferramentas** para chegar à causa.

Acessos: Grafana http://127.0.0.1:3000 · Jaeger http://127.0.0.1:16686 · Prometheus http://127.0.0.1:9090.

## Método RED

Para qualquer serviço, olhe três sinais (a base dos 4 dashboards):

- **Rate** — requests/s. `rate(http.server.duration_milliseconds_count[5m])` ou os contadores de negócio (`chats_total`, `analyses_total`, `routes_total`, `searches_total`).
- **Errors** — taxa de falha. `blocked_total`/`blocks_total` (rejeições esperadas) vs 5xx (falha real). Circuit-open no dashboard Dependency Health.
- **Duration** — latência. `latency_ms_p95{stale="false"}` por serviço; histogramas OTel `http.server.duration_milliseconds_bucket` para percentis finos.

## Debugging por trace (Jaeger)

Toda `/v1/chat` gera um trace único encadeando os 5+ serviços. Para achar o hop lento:

1. Jaeger UI → Service `svc-orchestrator` → Find Traces (ou por `traceparent` se o cliente enviou um).
2. Abra o trace: cada span é um hop (`svc-orchestrator → guardrails → router → rag → inference`). O span mais largo é o gargalo.
3. Quase sempre o span largo é o **`svc-inference`** (geração LLM na GPU) — esperado (baseline §14.3). Se for outro hop, investigue ali.

Via API (o smoke usa isto):
```bash
# traces recentes do orchestrator
curl -s "http://127.0.0.1:16686/api/traces?service=svc-orchestrator&limit=5&lookback=1h" \
  | python3 -c 'import json,sys; [print(t["traceID"], sorted({p["serviceName"] for p in t["processes"].values()})) for t in json.load(sys.stdin)["data"]]'

# um trace específico pelo ID (ex.: correlacionar com traceparent enviado)
curl -s "http://127.0.0.1:16686/api/traces/<TRACE_ID>"
```

## Análise por métrica (Prometheus / PromQL)

O Prometheus raspa o agregador (`svc-observability /v1/prometheus`) + recebe métricas
OTLP do `svc-inference` (GenAI + HTTP). Consultas úteis (todas validadas no stack):

```promql
# Latência P95 por serviço (agregado do ecossistema)
latency_ms_p95{stale="false"}

# Serviços servindo métrica stale (upstream caiu) — deve ser vazio
latency_ms_p95{stale="true"}

# Throughput de chat e roteamento por camada
chats_total
by_layer_semantic  /  by_layer_lexical  /  by_layer_llm  /  by_layer_fallback

# Segurança: injections bloqueadas e rajadas
blocks_total{service="svc-guardrails"}
delta(blocks_total{service="svc-guardrails"}[10m])        # base do alerta InjectionBurst

# GenAI (OTLP do svc-inference): tokens e TTFT
ttft_ms_p95
# nomes OTel têm ponto → referenciar via {__name__="..."}
rate({__name__="gen_ai.client.token.usage_sum"}[5m])

# Duração HTTP server (histograma OTel) — P95
histogram_quantile(0.95, sum by (le) (rate({__name__="http.server.duration_milliseconds_bucket"}[5m])))
```

UI: Prometheus `:9090` → Graph → cole a query. Ou use os dashboards do Grafana, que já
encapsulam estas.

## Dashboards (Grafana)

| Dashboard | Responde | Painéis-chave |
|-----------|----------|---------------|
| **System Health** | O ecossistema está saudável? | agregador up, serviços stale, P50/P95 por serviço |
| **Request Flow** | Por onde passa o tráfego? | chats, fluxo por serviço, roteamento por camada, tokens |
| **Dependency Health** | Downstreams e recursos ok? | stale por serviço, TTFT inference, HITL pausados, ingests RAG |
| **Security** | Estamos sob ataque? | injections bloqueadas, chats bloqueados, rajada 10min, flags OOD |

## Alertas (Prometheus)

Definidos em `observability/prometheus/rules.yml`, visíveis em `:9090/alerts`:

| Alerta | Dispara quando | Ação |
|--------|----------------|------|
| `AggregatorDown` | `up{job="msvc-ecosystem"} == 0` por 1min | svc-observability fora → `make logs svc-observability`; sem ele não há telemetria |
| `ServiceScrapeStale` | algum serviço com `stale="true"` 2min | upstream caiu; ver qual no dashboard e `/health` dele |
| `LatencySpikeP95` | P95 > 5s (fora inference/orchestrator) 5min | hop não-LLM lento; trace no Jaeger |
| `InjectionBurst` | >10 injections bloqueadas em 10min | possível ataque; ver dashboard Security + logs do guardrails |

## Fluxo de investigação (colar tudo)

1. **Alerta ou `/health` degradado** → identifica o serviço.
2. **Grafana** (System/Dependency Health) → Rate/Errors/Duration: o quê está anormal.
3. **Jaeger** → trace de uma request afetada → qual hop.
4. **Prometheus** → PromQL no sinal específico para quantificar/confirmar.
5. **`docs/RUNBOOK.md`** → fix pelo sintoma identificado.

Nota: `latency_ms_p95` de `svc-inference` alto (dezenas de segundos) é **normal** —
é a geração LLM na GPU (ver §14.3). Não é incidente; só vira alerta se o *plano de
controle* (guardrails/router/rag) passar de 5s (`LatencySpikeP95`).
