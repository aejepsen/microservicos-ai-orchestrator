# Backlog do Programa — Evolução pós-roadmap (FASE 18)

Formalização da FASE 18 (Long-term Roadmap). O roadmap operacional (fases 8-17) está
**concluído**; o que segue é backlog de evolução — construível pelo mesmo método SDD
(spec ultra-elaborada → agente em loop → gates G1-G8). Não é implementação agora:
é a fila priorizada, com dependências e ordem.

Duas correntes de trabalho:
- **Corrente A — Aprimoramentos dos 7 serviços:** as decisões deferidas em aberto
  (`SDD/DEFERRED_SPECS.md`, DS-02..DS-17; DS-01 e DS-05 já resolvidas). Cada uma já
  tem contrato/gates esboçados lá.
- **Corrente B — Serviços novos:** 6 capacidades do §18.1. Spec-esboços abaixo.

## Priorização (tiers)

Critério: valor × (1/esforço) respeitando dependências. Um item só sobe de tier quando
suas dependências estão no tier igual ou acima.

### P0 — Fundação (desbloqueia o resto)

| Item | Serviço | Por quê primeiro | Dependência |
|------|---------|------------------|-------------|
| **DS-02** persistência de evals (SQLite→Postgres) | svc-evals | Sobe Postgres no compose; desbloqueia DS-03/15/17 | — |
| **DS-04** deadline global por request (504) | svc-orchestrator | Robustez, pequeno, alto valor | — |

### P1 — Alto valor, autônomos

| Item | Serviço/novo | Valor | Dependência |
|------|--------------|-------|-------------|
| **svc-cache** (Corrente B) | novo | Corta latência/custo (cache de respostas+embeddings); resolve DS-07 | — |
| **DS-08** re-ranking L2 + multi-query | svc-rag | Qualidade de retrieval | — |
| **DS-09** guardrails EN + moderação (PII/toxicidade) | svc-guardrails | Segurança + i18n | — |
| **DS-06** backends vLLM/TGI + roteamento por modelo | svc-inference + svc-router | Escala de inferência (throughput real) | GPU/infra |

### P2 — Novas capacidades (gateadas por fundação)

| Item | Serviço/novo | Valor | Dependência |
|------|--------------|-------|-------------|
| **svc-auth** (Corrente B) | novo | OAuth2/OIDC + multi-tenancy + RBAC; gate de audit/analytics | — |
| **DS-03 + DS-16** conversa longo prazo + HITL tool-call/LangGraph | svc-orchestrator | Memória de thread + controle fino | DS-02 (Postgres) |
| **DS-13** conectores de fonte (Drive/S3/crawler) | svc-rag | Ingestão real de dados corporativos | — |
| **DS-11** alerting/paging + TSDB longo prazo | svc-observability | Retenção + notificação (hoje: regras Prometheus in-stack) | — |

### P3 — Evolução posterior

| Item | Serviço/novo | Dependência |
|------|--------------|-------------|
| **svc-audit** (Corrente B) — log imutável (compliance/billing) | novo | svc-auth |
| **svc-analytics** (Corrente B) — BI (tendências, comportamento) | novo | svc-auth, svc-audit |
| **svc-admin** (Corrente B) — API de gestão (thresholds, políticas) | novo | svc-auth |
| **svc-webhook** (Corrente B) — eventos outbound | novo | svc-auth |
| **DS-10** rate-limit-as-a-service (`/v1/gate`) | svc-guardrails | svc-auth |
| **DS-12** registro dinâmico de upstreams | svc-observability | — |
| **DS-14** comunidades Louvain offline | svc-rag | — |
| **DS-15** aprendizado de exemplares por feedback | svc-router | DS-02 |
| **DS-17** UI de evals + geração automática de goldens | svc-evals | DS-02 |

---

## Corrente B — Spec-esboços dos 6 serviços novos

Formato condensado do `SDD/SPEC_TEMPLATE.md` (metadados · objetivo · não-objetivos ·
contrato-núcleo · dependências · gates-chave). Cada esboço vira spec completa (14
seções) quando entrar em construção, seguindo a ordem de `ARCHITECTURE.md §4`.

### svc-cache (P1) — camada de cache

- **Objetivo:** reduzir latência e custo cacheando resultados determinísticos (respostas de chat idênticas, embeddings, decisões de rota) com TTL e invalidação.
- **Não-objetivos:** não é fonte de verdade; não persiste após TTL; não cacheia respostas com `allow_write`; não substitui Qdrant; não guarda PII sem hashing.
- **Contrato-núcleo:** `GET/PUT /v1/cache/{namespace}/{key}` + `DELETE` (invalidação); backend Redis; chave = hash do input normalizado. Transversal: `X-Internal-Key`, `/health`, `/metrics`, OTel.
- **Dependências:** Redis (novo no compose, rede `backend internal`). Consumido por orchestrator (respostas) e router (decisões).
- **Gates-chave:** hit/miss corretos; TTL honrado; invalidação; isolamento por namespace/tenant; fail-open (cache fora ⇒ segue sem cache, nunca derruba request); P95 overhead < 5ms.

### svc-auth (P2) — identidade e multi-tenancy

- **Objetivo:** OAuth2/OIDC + emissão/validação de tokens + RBAC + isolamento por `tenant_id`. Passa a ser a fronteira de identidade do ecossistema.
- **Não-objetivos:** não substitui o `X-Internal-Key` interno (auth serviço-a-serviço permanece); não guarda senha em claro; não é IdP completo (federa a um externo).
- **Contrato-núcleo:** `POST /v1/token`, `POST /v1/introspect`, `GET /v1/userinfo`; JWT RS256 (rejeita `none`); `tenant_id` + `scopes` nos claims. Injeta contexto de tenant nos downstreams.
- **Dependências:** Postgres (usuários/tenants) — reusa o de DS-02. IdP externo (OIDC).
- **Gates-chave:** rejeita `alg:none`; introspect timing-safe; RBAC vertical/horizontal; **cross-tenant isolation testado** (usuário A não acessa dado de B); refresh rotation; sem user enumeration.

### svc-audit (P3) — log imutável

- **Objetivo:** trilha append-only de eventos sensíveis (quem/o quê/quando/tenant) para compliance, forense e billing.
- **Não-objetivos:** não permite update/delete (imutável); não é log de aplicação (só eventos de negócio/segurança); não guarda payloads com PII sem redação.
- **Contrato-núcleo:** `POST /v1/audit` (append), `GET /v1/audit?filter` (consulta), encadeamento por hash (tamper-evident). Formato do §13.2 do NEXT_PHASES.
- **Dependências:** svc-auth (tenant/identidade), armazenamento append-only (Postgres WORM ou object store).
- **Gates-chave:** imutabilidade (tentativa de update ⇒ 405); cadeia de hash verificável; sem PII/secret no log; isolamento por tenant; retenção configurável.

### svc-analytics (P3) — BI

- **Objetivo:** métricas de negócio agregadas (tendências de domínio, comportamento, uso por tenant) sobre os eventos de audit + métricas do observability.
- **Não-objetivos:** não é o observability (que é operacional/RED); não faz decisão em tempo real; read-only sobre dados já coletados.
- **Contrato-núcleo:** `GET /v1/analytics/{report}` com janelas temporais; materialização offline. Dashboards Grafana dedicados.
- **Dependências:** svc-audit (fonte de eventos), svc-auth (escopo por tenant).
- **Gates-chave:** agregações corretas vs golden; isolamento por tenant; sem vazamento cross-tenant em relatórios; latência de query aceitável.

### svc-admin (P3) — API de gestão

- **Objetivo:** operações administrativas versionadas — atualizar modelo, ajustar thresholds (OOD, rota), mudar políticas — sem redeploy.
- **Não-objetivos:** não bypassa gates de segurança; não edita dados de negócio; toda ação é auditada.
- **Contrato-núcleo:** `POST /v1/admin/{recurso}` (RBAC admin-only), cada mutação → evento no svc-audit. Ex.: refit OOD, tuning de threshold, hot-reload de política.
- **Dependências:** svc-auth (RBAC admin), svc-audit (trilha), serviços-alvo (endpoints de reconfiguração).
- **Gates-chave:** admin-only (403 p/ não-admin); toda ação audita; rollback de config; validação de input.

### svc-webhook (P3) — eventos outbound

- **Objetivo:** entrega de eventos do ecossistema a consumidores externos (write completado, novo domínio registrado) com retry e assinatura.
- **Não-objetivos:** não é fila interna (usar mecanismo interno p/ isso); não garante ordenação global; não entrega sem assinar.
- **Contrato-núcleo:** registro de webhook (`POST /v1/webhooks`), entrega com HMAC signature + retry exponencial + DLQ. **Anti-SSRF na URL de callback** (reusa o guard do padrão transversal).
- **Dependências:** svc-auth (dono do webhook por tenant), mecanismo de retry.
- **Gates-chave:** assinatura HMAC verificável; retry/backoff; **SSRF bloqueado** (callback não acessa rede interna); isolamento por tenant; idempotência de entrega.

---

## Ordem recomendada de construção

```
P0: DS-02 (Postgres/evals) ──┬─► DS-03+DS-16 (conversa+LangGraph)
                             ├─► DS-15 (feedback router)
                             └─► DS-17 (UI evals)
    DS-04 (deadline 504)  [independente, rápido]

P1: svc-cache        [independente]
    DS-08 (RAG L2)   [independente]
    DS-09 (moderação)[independente]
    DS-06 (vLLM)     [infra GPU]

P2: svc-auth ──┬─► svc-audit ──► svc-analytics
               ├─► svc-admin
               ├─► svc-webhook
               └─► DS-10 (rate-limit-as-a-service)
    DS-13 (conectores), DS-11 (TSDB/paging)  [independentes]
```

**Regra herdada do programa:** cada item entra por spec completa antes de código;
gates G1-G8 na mesma execução são a definição de DONE; baselines medidos do AIO/stack
atual; golden não é ajustável para passar gate. Ao concluir um item: as-built no
`DEFERRED_SPECS.md` (Corrente A) ou spec própria (Corrente B) + `graphify update .`.

## Estado do roadmap (2026-07-07)

Fases 8-10 e 12-17: **concluídas**. Fase 11 (Kubernetes): **skipped** (sem cluster alvo).
Fase 18: **formalizada como este backlog**. O sistema está operacional e completo
(deploy + CI/CD + observabilidade + segurança + DR + docs); a evolução daqui é
incremental e priorizada acima. **Roadmap encerrado.**
