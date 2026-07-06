# SDD — Spec-Driven Development com Agentes em Loop

Specs ultra-elaboradas para construção de microsserviços independentes por agentes autônomos, derivados das capacidades validadas do **AI-Orchestrator** (`../AI-Orchestrator`).

## Método

```
SPEC_TEMPLATE.md ──derivação──▶ specs/spec-svc-*.md ──loop de agentes──▶ repo do serviço
        ▲                                                    │
        └────────────── calibração (só no piloto) ◀──────────┘
```

1. **Rodada 1 (piloto):** `specs/spec-svc-guardrails.md` → loop de agentes constrói o serviço real. Menor superfície, sem dependências de infra, gates já medidos no AIO.
2. **Retrospectiva do piloto:** onde o agente travou/inventou? Gates verificáveis por comando? Custo (tempo/tokens)? → corrigir `SPEC_TEMPLATE.md` **uma vez**.
3. **Rodada 2:** gerar as 6 specs restantes a partir do template calibrado (ordem em `ARCHITECTURE.md` §Ordem de construção).

## Arquivos

| Arquivo | Papel |
|---------|-------|
| `SPEC_TEMPLATE.md` | Template canônico — toda spec deriva dele; mudanças aqui propagam para specs futuras |
| `ARCHITECTURE.md` | Mapa dos 7 serviços, contratos transversais (auth, OTel, health, versionamento), ordem de construção |
| `specs/spec-svc-guardrails.md` | Spec do piloto (única gerada até o piloto passar nos gates) |

## Regras do processo

- **Nenhuma spec nova antes do piloto passar em todos os gates.** Erro de template multiplicado por 7 é caro.
- Specs carregam **baselines medidos do AIO** (AUC 0.980, 0/6 injection, 97.5% faithfulness, 94.1% routing) — alvo concreto + rastreabilidade de regressão.
- Todo critério de aceite é **machine-checkable**: comando exato + threshold numérico. "Boa cobertura" não existe aqui.
- Integração entre serviços é **contract-first** (OpenAPI versionado + padrões transversais). Zero código compartilhado.
