# SLA & Objetivos de Serviço

Alvos operacionais do stack single-node (1× RTX 3060). Números derivados do baseline
medido na Fase 14 (`SDD/NEXT_PHASES.md §14.3`), não aspiracionais.

> Escopo: single-node. Alvos de alta disponibilidade (multi-réplica, failover
> automático) exigem a Fase 11 (Kubernetes, skipped) ou a Fase 18 (cluster GPU).

## SLOs (Service Level Objectives)

| Indicador | Alvo | Baseline medido | Como medir |
|-----------|------|-----------------|------------|
| Latência plano de controle (P95) | < 200ms | 117ms @ 245 rps | `make loadtest` (cenário light) |
| Latência chat single (P95) | < 5s | 3.7s | `make loadtest` (cenário chat) |
| Throughput plano de controle | ≥ 200 rps | 245 rps | idem |
| Throughput chat | ~0.3 req/s (1 GPU) | 0.32 req/s | idem |
| Taxa de erro | < 0.1% | 0% | Grafana / `make loadtest` |
| Circuit-open rate | < 1% | 0% | Grafana (dashboard Dependency Health) |

Capacidade honesta: **~1 chat concorrente** com P95 3.7s + plano de controle a
~245 rps. A geração LLM é o limite físico; escalar chat = mais GPUs.

## RTO / RPO (recuperação)

| Componente | RTO | RPO | Mecanismo |
|------------|-----|-----|-----------|
| Qdrant (vetores) | sub-segundo medido (alvo 5min) | = frequência do backup | `make restore` |
| svc-* (stateless) | ~1min (redeploy) | N/A | imagem GHCR |
| Grafana/Prometheus | redeploy | 0 / lossy-ok | git / TSDB |
| Ollama (modelos) | ~10min (redownload) | N/A | volume |

RPO do Qdrant depende do agendamento do `make backup` — cron diário dá 24h; reduzir o
intervalo se o negócio exigir 1h.

## Monitoramento

- **Grafana** (`:3000`): 4 dashboards — System Health, Request Flow, Dependency Health, Security.
- **Alertas Prometheus** (`observability/prometheus/rules.yml`): `AggregatorDown`,
  `ServiceScrapeStale`, `LatencySpikeP95`, `InjectionBurst`.
- **Traces** (`:16686`): latência por hop, cadeia orchestrator→guardrails→router→rag→inference.

## Resposta a incidentes

1. **Detectar** — alerta no Prometheus/Grafana ou `/health` degradado.
2. **Diagnosticar** — `docs/RUNBOOK.md` pelo sintoma; Jaeger para o hop lento.
3. **Mitigar** — restart do serviço afetado; circuit breaker isola downstream automaticamente.
4. **Recuperar dados** (se aplicável) — `make restore`.
5. **Pós** — registrar causa raiz; se recorrente, virar item de backlog/decisão.

Sendo single-node, não há failover automático — a mitigação é redeploy do serviço
(`docker compose up -d <svc>`), segundos para stateless.
