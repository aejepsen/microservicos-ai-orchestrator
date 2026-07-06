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
| svc-observability | ⏳ próximo (rodada 6) | — |
| svc-orchestrator | ⏳ aguarda spec (rodada 7) | — |

**Regra do programa:** nenhuma spec nova antes do piloto passar todos os gates. O piloto (svc-guardrails) calibrou o template — as 5 correções da retrospectiva (`SDD/RETRO.md`) já estão aplicadas em `SDD/SPEC_TEMPLATE.md`. `spec-svc-evals` foi gerada a partir do template calibrado.

## Construído por

Claude Fable 5 (`claude-fable-5`) executando o loop de agentes SDD.
