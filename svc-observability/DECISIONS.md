# DECISIONS — svc-observability

Desvios da SPEC e decisoes tecnicas com justificativa.

## D1 — Agregador, nao Collector OTLP
svc-observability RASPA o /metrics dos servicos (pull) e agrega; NAO recebe OTLP (isso e o otel-collector, infra). Escopo §3. Reproduz o papel do metrics.py/eval_results.py do AIO (que tambem raspava o Prometheus do Collector como fonte independente).

## D2 — Scraper adapter + FakeScraper
HttpScraper (prod, raspa /metrics com UPSTREAM_KEY) + FakeScraper deterministico (gates, offline). Padrao adapter+fake do template §8.5. Nenhum gate exige upstream no ar.

## D3 — Fonte inegociavel; derivados nascem estimate
Raspado=live, ingerido=eval (com dataset_date), computado=estimate. Derivados (ex.: ecosystem_tokens_total) sao ESTIMATE por construcao no aggregator — nunca podem virar live. G3 tem a armadilha explicita. Reproduz o fix do dashboard do AIO (faithfulness le eval real, nao valor fixo).

## D4 — Degradacao com cache stale
Upstream fora no scrape: servico marcado ok=false, metricas antigas mantidas com stale=true. Cache stale melhor que zero observabilidade (padrao MetricsCollector do AIO). G2 cobre.

## D5 — Prometheus em texto puro (sem client pesado)
Exposicao gerada a mao (# HELP / # TYPE / linhas name{labels} value) — formato simples, evita dependencia. Nome sanitizado, labels escapados. G4 reparseia o texto para validar.

## D6 — Anti-SSRF nas URLs de upstream
URLs de upstream (config de operador) validadas no boot: so http/https, bloqueio metadata/loopback salvo ALLOW_LOCAL_UPSTREAM=1 (dev: upstreams sao service names/localhost). Teste de allow usa IP literal (template §8.5). G7 cobre.

## D7 — Export OTLP de metricas para SaaS (opt-in, fail-open)
Alem do pull local (API + /v1/prometheus), OTLP_METRICS_ENABLED=1 liga push OTLP HTTP das metricas agregadas (otel_metrics.py): cada nome vira ObservableGauge com atributos service/source/stale — a fonte (D3) viaja no export; derivados chegam ao SaaS como estimate, nunca live. Endpoint/auth pelas envs padrao OTel (OTEL_EXPORTER_OTLP_ENDPOINT/HEADERS — ex.: Grafana Cloud). Default OFF = on-premise puro, gates offline intactos. Fail-open: SaaS fora → warning em background, scrape/API nunca bloqueiam (espelho do fail-closed de entrada). Instrumentos registrados lazy via sync() pos-refresh/ingest (nome inedito entra no ciclo de export seguinte). Gates G-OTLP-1/2/3 em tests/test_otel_metrics.py.

## Desvios da SPEC
Nenhum desvio funcional. Registro dinamico de upstreams, alerting e TSDB ficam no BACKLOG (v1 = upstreams por config). D7 e extensao alem da SPEC v1 (export push opt-in), documentada aqui e no README.
