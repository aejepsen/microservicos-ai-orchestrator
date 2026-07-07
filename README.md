# microservicos-ai-orchestrator

Ecossistema de microsserviços independentes derivados do **AI-Orchestrator**, construídos por **spec-driven development (SDD) + agentes em loop**. Cada serviço nasce de uma spec ultra-elaborada, é construível do zero por agente autônomo e integrável aos demais via contrato versionado.

## Estrutura

```
microservicos-ai-orchestrator/
  SDD/                     # método: template de spec, arquitetura, specs congeladas
    README.md
    SPEC_TEMPLATE.md
    ARCHITECTURE.md        # 7 serviços, contratos transversais, ordem de construção
    specs/spec-svc-*.md
  svc-guardrails/          # PILOTO — injection + OOD + sanitização (repo próprio)
  <svc-router>/            # próximos serviços entram aqui, um diretório cada
  ...
```

Cada `svc-*` é um repositório git independente (contract-first; zero código compartilhado). Integração futura via OpenAPI `/v1/` + padrões transversais (auth `X-Internal-Key`, OTel GenAI, `/health`, `/metrics`).

## Os 7 serviços (ver SDD/ARCHITECTURE.md)

`svc-guardrails` (piloto) · `svc-evals` · `svc-inference` · `svc-router` · `svc-rag` · `svc-observability` · `svc-orchestrator`

## Estado

| Serviço | Status | Gates |
|---------|--------|-------|
| svc-guardrails | ✅ DONE (piloto) | G1–G8 todos PASS (ver svc-guardrails/README.md) |
| svc-evals | ✅ DONE (rodada 2) | G1–G8 todos PASS (ver svc-evals/README.md) |
| svc-inference | ✅ DONE (rodada 3) | G1–G8 todos PASS (ver svc-inference/README.md) |
| svc-router | ✅ DONE (rodada 4) | G1–G8 todos PASS (ver svc-router/README.md) |
| svc-rag | ✅ DONE (rodada 5) | G1–G8 todos PASS (ver svc-rag/README.md) |
| svc-observability | ✅ DONE (rodada 6) | G1–G8 todos PASS (ver svc-observability/README.md) |
| svc-orchestrator | ✅ DONE (rodada 7) | G1–G8 todos PASS (ver svc-orchestrator/README.md) |

**7/7 serviços DONE.** Roadmap pós-SDD (18 fases, `SDD/NEXT_PHASES.md`): fases 8-10, 12-16 concluídas · fase 11 (Kubernetes) skipped · próxima: 17. Stack de produção sobe com `make up` + `make smoke-test`.

## Operação (stack de produção)

```bash
cp .env.example .env    # gere INTERNAL_KEY, QDRANT_API_KEY, GRAFANA_PASSWORD
make up                 # sobe os 7 serviços + Ollama/Qdrant + observabilidade
make smoke-test         # valida ponta a ponta (10 asserts)
```

## Documentação

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — topologia as-built, portas, redes, fluxo do `/v1/chat`
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — deploy passo a passo, segredos, rollback
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — troubleshooting por sintoma (503/403/401/422, latência, circuito, OOD, recovery)
- [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) — endpoints `/v1/` por serviço + exemplos
- [`docs/SLA.md`](docs/SLA.md) — SLOs, RTO/RPO, resposta a incidentes
- [`SDD/NEXT_PHASES.md`](SDD/NEXT_PHASES.md) — roadmap 18 fases com as-built de cada uma

## Construído por

Claude Fable 5 (`claude-fable-5`) executando o loop de agentes SDD.
