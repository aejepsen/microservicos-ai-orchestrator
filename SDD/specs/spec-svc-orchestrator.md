# SPEC — svc-orchestrator v1.0

> Sétima e ÚLTIMA spec do programa SDD (rodada 7). Derivada de `../SPEC_TEMPLATE.md` calibrado por RETRO rodadas 1–6. Serviço de integração: amarra guardrails + router + rag + inference.

---

## 0. Metadados

| Campo | Valor |
|-------|-------|
| Serviço | `svc-orchestrator` |
| Versão da spec | 1.0.0 |
| Status | **DONE** (as-built §15; congelada como frozen em 2026-07-06) |
| Baseline de referência | AI-Orchestrator `fe3adc1` — `gateway/graph.py` (fan-out/fan-in LangGraph), `gateway/write_intent.py` (HITL), `gateway/tools/circuit.py`, `main.py` (SSE) |
| Repo alvo | `~/Documentos/projeto-portifolio/microservicos-ai-orchestrator/svc-orchestrator` |
| Data de congelamento | 2026-07-06 |

## 1. Contexto e problema

É o coração do AI-Orchestrator: recebe uma pergunta, aplica **guardrails** (sanitização/injection/OOD), **roteia** para domínio(s), faz **fan-out** para agentes de domínio (cada um recupera contexto via RAG e sintetiza via LLM), faz **fan-in** numa síntese final, com **HITL** (pausa em operações de escrita) e **streaming SSE** ao vivo. Vive em `graph.py` + `write_intent.py` + `main.py`, com 410 testes e fan-out de 3 domínios em ~19.5s.

Este serviço extrai a **orquestração** para uma API independente que **consome os outros 4 serviços do ecossistema** via HTTP: `svc-guardrails` (pré-rota), `svc-router` (decisão de domínio), `svc-rag` (contexto por domínio), `svc-inference` (síntese). É o **teste de integração do ecossistema inteiro** — o último serviço, de propósito (ARCHITECTURE §4).

Padrão herdado (template §8.5): **cada downstream é um client-adapter + fake determinístico**; os gates rodam com fakes (100% offline, sem nenhum outro serviço no ar). Circuit breaker por downstream (padrão AIO: 3 falhas de transporte → OPEN; 4xx não conta). **Tracing distribuído** (decisão da rodada 7): propaga `traceparent` (W3C) para todos os downstream + logs.

Lição institucionalizada: o golden de HITL carrega **armadilha** — frase nominal ("contas a pagar") NÃO é operação de escrita; leitura nunca pausa (§12.7).

## 2. Objetivo (uma frase)

Orquestrar o fluxo guardrails → router → fan-out de agentes de domínio (rag + inference) → fan-in de síntese, com HITL determinístico em escrita e streaming SSE, consumindo os serviços do ecossistema via adapters, testável 100% offline com downstreams fake.

## 3. Não-objetivos (o agente NÃO constrói)

- Reimplementar guardrails/router/rag/inference — **consome** os serviços via HTTP.
- Servir LLM / embeddings / vector store — tudo via downstream.
- Persistência de conversas de longo prazo — checkpoint em memória por `thread_id` (histórico rico → BACKLOG).
- UI / frontend — serve SSE; o cliente é outro componente.
- Autenticação de usuário final / multi-tenancy — auth interna do ecossistema apenas.
- Novos domínios de negócio — os domínios vêm do router; agentes são genéricos (rag+inference por domínio).
- Geração de relatórios / analytics — isso é svc-observability.

## 4. Glossário

| Termo | Definição neste contexto |
|-------|--------------------------|
| Pipeline/grafo | sanitize → route → fan-out → fan-in → final |
| Fan-out | Disparar um agente por domínio decidido pelo router |
| Fan-in | Consolidar as respostas dos agentes numa síntese |
| Agente de domínio | Passo que, para um domínio, busca contexto (rag) e responde (inference) |
| HITL | Human-in-the-loop: pausa antes de despachar uma operação de escrita |
| Write intent | Detecção determinística de operação de escrita (léxico PT) |
| Thread | Sessão identificada por `thread_id`; guarda checkpoint p/ resume |
| SSE | Server-Sent Events: `route` → `agent` (por domínio) → `final` |
| Downstream | Serviço consumido: guardrails, router, rag, inference |
| `traceparent` | Header W3C propagado a todos os downstream (tracing distribuído) |
| Armadilha | Frase nominal com verbo-substantivo ("contas a pagar") que NÃO é escrita |

## 5. Contrato de API

> Fonte da verdade: `api/openapi.yaml` (OpenAPI 3.1), gerado na F1, validado com `openapi-spec-validator`. Rotas `/v1/`.

### 5.1 Endpoints

| Método | Rota | Auth | Descrição | Erros |
|--------|------|------|-----------|-------|
| POST | `/v1/chat` | interna | Orquestra a pergunta; `stream=true` → SSE (`route`/`agent`/`final`); pode pausar (HITL) | 401, 422, 403 (guardrails bloqueou), 503 (downstream/circuito), 504 |
| POST | `/v1/chat/{thread_id}/resume` | interna | Retoma após pausa HITL (aprovar/rejeitar a escrita) | 401, 404 (thread sem pausa), 422 |
| GET | `/v1/threads/{thread_id}` | interna | Estado de uma thread (pendente de HITL? última resposta) | 401, 404 |
| GET | `/health` | nenhuma | Liveness + readiness (deps: cada downstream) | — |
| GET | `/metrics` | interna | Contadores (chats, por-camada, HITL, blocks) + latências; `source: live` | 401 |

### 5.2 Schemas principais (Pydantic v2 espelha o OpenAPI)

```yaml
ChatRequest: {query: str, thread_id?: str, stream: bool = false, allow_write: bool = false}
AgentResult: {domain: str, answer: str, context_used: int}
ChatResponse:                 # stream=false
  thread_id: str
  decision: "answered" | "blocked" | "paused"
  domains: list[str]
  agents: list[AgentResult]
  final: str | null
  pending_write: object | null  # presente se decision=paused
# stream=true: SSE de eventos {type: "route"|"agent"|"final"|"blocked"|"paused"|"error", data}
ResumeRequest: {approve: bool}

Erro de negócio: 422 {error, detail, rule}
Erro interno: 500 genérico — stack só em log.
```

### 5.3 Fluxo (grafo)
1. **sanitize/guardrails**: chama svc-guardrails `/v1/analyze`. `decision=block` → evento `blocked`, 403 (não-stream). `flag` (OOD) → segue com marca.
2. **route**: chama svc-router `/v1/route` → domínios. Evento `route`.
3. **fan-out**: para cada domínio, agente = svc-rag `/v1/search` (contexto) + svc-inference `/v1/chat/completions` (resposta). Evento `agent` por domínio concluído.
4. **HITL**: se a pergunta tem **write intent** e `allow_write=false` → **pausa** (evento `paused`, guarda checkpoint), aguarda `/resume`. `allow_write=true` ou leitura → segue.
5. **fan-in**: síntese final via svc-inference (multi-domínio) ou resposta direta (single). Evento `final`.

### 5.4 Contrato de erro
- Guardrails bloqueou: `403` (não-stream) / evento `blocked` (stream). Write intent + não aprovado: `paused`.
- Downstream fora / circuito OPEN: `503`. Deadline: `504`. Negócio: `422 {error, detail, rule}`. Interno: `500` genérico.

## 6. Modelo de dados e estado

- **Estado de processo**: checkpoints por `thread_id` (dict em memória: query, domínios, resultados parciais, write pendente). TTL/limite de threads para não crescer sem limite. Reinício perde threads (histórico longo → BACKLOG).
- **Sem banco, sem modelo local.** Toda capacidade pesada é downstream.
- Isolamento de artefatos (template §6): N/A.

## 7. Configuração (env — 12-factor)

| Variável | Default | Obrigatória | Efeito |
|----------|---------|-------------|--------|
| `INTERNAL_KEY` | — | sim (prod) | Auth interna (deste serviço); ausente → 401 (fail-closed) |
| `ALLOW_OPEN_ACCESS` | `0` | não | `1` libera sem key (dev) |
| `DOWNSTREAM_KEY` | — | não | X-Internal-Key usado para chamar os downstream |
| `GUARDRAILS_URL` | `http://svc-guardrails:8200` | não | Endpoint do svc-guardrails |
| `ROUTER_URL` | `http://svc-router:8203` | não | Endpoint do svc-router |
| `RAG_URL` | `http://svc-rag:8204` | não | Endpoint do svc-rag |
| `INFERENCE_URL` | `http://svc-inference:8202` | não | Endpoint do svc-inference |
| `MODEL` | — | não | Modelo passado ao svc-inference |
| `HITL_ENABLED` | `0` | não | `1` liga a pausa em write intent |
| `RAG_ENABLED` | `1` | não | `0` pula a busca de contexto no agente |
| `MAX_THREADS` | `1000` | não | Limite de threads em memória (eviction) |
| `REQUEST_DEADLINE_S` | `120` | não | Deadline global por request (504) |
| `DOWNSTREAM_TIMEOUT_S` | `30` | não | Timeout por chamada a downstream |
| `CIRCUIT_FAIL_THRESHOLD` | `3` | não | Falhas de transporte → OPEN (por downstream) |
| `ALLOW_LOCAL_DOWNSTREAM` | `0` | não | `1` permite downstream em loopback/rede interna (dev) |
| `RATE_LIMIT_PER_MIN` | `120` | não | Sliding window por IP |
| `OTEL_ENABLED` | `0` | não | OTLP → Collector; fora = no-op |
| `LOG_LEVEL` | `INFO` | não | Log JSON estruturado |

> Fail-closed na auth; degradação graceful nos downstream (fora → 503 limpo + circuito, nunca crash).

## 8. NFRs

### 8.1 Segurança
- Transversais (ARCHITECTURE §3.1): `hmac.compare_digest`, fail-closed, Swagger off, `.dockerignore`, `.env` fora do git.
- URLs de downstream (config de operador): validar esquema http/https + bloquear metadata/loopback salvo `ALLOW_LOCAL_DOWNSTREAM=1`.
- **Guardrails é a primeira barreira**: query hostil passa por svc-guardrails antes de qualquer coisa; `block` corta o fluxo.
- Query/contexto são dados não confiáveis: nunca em log sem escape; nunca ecoados em erro.

### 8.2 Performance
- **Overhead de orquestração** (downstreams fake, exclui tempo real de LLM): **P95 < 50 ms** no fluxo single-domínio não-streaming.
- Latência real (com inference/rag): dominada pelos downstream — medida e reportada, não gateada.

### 8.3 Observabilidade
- **Tracing distribuído**: gera/propaga `traceparent` (W3C) para TODOS os downstream; inclui no log de cada passo. (Resolve o gap D7 no ponto de integração.)
- `/metrics`: `chats_total`, `blocked_total`, `paused_total`, `by_domain`, `latency_p50/p95`; `source: live`.
- Log JSON por passo: `{trace_id, step, domains, decision, latency_ms}`.
- Spans OTel GenAI: N/A aqui (a geração é do svc-inference, que instrumenta); spans HTTP próprios → BACKLOG.

### 8.4 Resiliência
- **Circuit breaker por downstream** (padrão AIO): 3 falhas de transporte → OPEN por reset; 4xx não conta. OPEN → 503 sem bater no downstream.
- Guardrails fora → **fail-closed de segurança**: sem a análise, o fluxo é recusado (503), NÃO segue sem guardrails (segurança não degrada aberta).
- Router/rag/inference fora → 503 limpo no passo; SSE encerra com evento `error`.
- **Deadline** global → 504. Fan-out parcial: se um agente falha, a síntese usa os que responderam + marca o domínio faltante (degradação explícita).
- HITL: checkpoint persiste a pausa; `/resume` retoma; thread inexistente → 404.

## 9. Dependências

| Dependência | Tipo | Runtime obrigatória? | Se ausente |
|-------------|------|----------------------|------------|
| svc-guardrails | serviço | **sim** (fail-closed de segurança) | 503 — fluxo recusado |
| svc-router | serviço | sim | 503 no passo route |
| svc-inference | serviço | sim (síntese) | 503 no passo agent/final |
| svc-rag | serviço | não (`RAG_ENABLED=0` pula) | agente sem contexto; segue |
| OTel Collector | infra | não | no-op |

> Gates: TODOS os downstream via **FakeClient** determinístico. Nenhum gate exige outro serviço no ar. Smoke com o ecossistema real (`docker compose`) é separado e opcional.

## 10. Gates de aceitação

> Velocidade: todos **rápidos** (downstreams fake, sem modelo, sem rede). `make gates` roda todos na mesma execução.

| # | Gate | Velocidade | Comando | Threshold | Baseline AIO |
|---|------|-----------|---------|-----------|--------------|
| G1 | Testes | rápido | `python -m pytest -q` | 100% pass, ≥ 55 testes | 410 (AIO todo) |
| G2 | Fluxo de orquestração | rápido | `python evals/eval_flow.py` | sanitize→route→fan-out→fan-in correto; single e multi-domínio; guardrails block corta | fan-out/fan-in graph.py |
| G3 | HITL write-intent + armadilha | rápido | `python evals/eval_hitl.py` | escrita pausa; leitura não; **armadilha "contas a pagar" não pausa**; resume retoma | write_intent.py |
| G4 | SSE + resiliência | rápido | `python evals/eval_sse.py` | sequência de eventos route→agent→final; downstream fora → evento `error`; guardrails fora → fluxo recusado (fail-closed) | breaker 3→OPEN |
| G5 | Lint + tipos | rápido | `ruff check . && python -m mypy src/` | 0 erros | — |
| G6 | Contrato | rápido | `openapi-spec-validator api/openapi.yaml && python -m pytest tests/test_contract.py` | 0 violações; toda rota testada | — |
| G7 | Security + traceparent | rápido | `python -m pytest tests/test_security.py` | fail-closed, 401, SSRF, guardrails-fail-closed, **traceparent propagado aos downstream** | auditoria 0 |
| G8 | Perf (overhead) | rápido | `python evals/bench_latency.py` | P95 < 50 ms (fake downstreams, single) | — |

**Dogfood (o agente constrói em F2–F4):**
- *FakeClients determinísticos* para guardrails/router/rag/inference: respostas previsíveis, configuráveis para bloquear (guardrails), rotear multi-domínio (router), falhar (transporte/4xx).
- *eval_flow*: query single → 1 agente; multi → fan-out; guardrails block → sem route.
- *eval_hitl*: query de escrita ("cadastre um funcionário") pausa; leitura ("qual o saldo") não; **armadilha** ("relatório de contas a pagar") não pausa; resume(approve) conclui.
- *eval_sse*: coleta eventos; ordem e tipos corretos; injeta falha de downstream → evento `error` limpo; guardrails fora → recusa (fail-closed).

## 11. Plano de fases

| Fase | Entregável | Verificação | Stop condition |
|------|-----------|-------------|----------------|
| F0 | Scaffold robusto (template §11): repo no destino, todos os dirs de uma vez, pyproject, Dockerfile, Makefile (`python -m`), CI, SPEC.md | `docker build .` + `make check` + `.venv/bin/python` existe | build verde |
| F1 | `api/openapi.yaml` + schemas Pydantic (ChatRequest/Response/Resume) | G6 | contrato validado |
| F2 | Clients (Fake+Http) dos 4 downstream + circuit breaker + traceparent + testes | G1 subset + G5 | clients verdes |
| F3 | Grafo (sanitize→route→fan-out→fan-in) + write_intent + `eval_flow.py` | G2 | fluxo correto |
| F4 | HITL (pausa/checkpoint/resume) + SSE (eventos + resiliência) + `eval_hitl.py` + `eval_sse.py` | G3 + G4 | HITL+SSE PASS |
| F5 | API completa (`/v1/chat`, `/resume`, `/threads`) + auth + SSRF + rate-limit + deadline | G6 + G7 | security PASS |
| F6 | `/health` (deps downstream) + `/metrics` + logs + traceparent nos logs | smoke via compose | telemetria ok |
| F7 | Bench + README (gates medidos + diagrama do fluxo) + DECISIONS.md + `make smoke` (ecossistema real, opcional) | **G1–G8 todos na mesma execução** | **DONE** |

## 12. Regras para o agente

1. Escopo = esta spec. Fora → `BACKLOG.md`.
2. Contradição/gate impossível → PARAR e perguntar.
3. Mesmo gate falhando após 3 correções distintas → parar, diagnóstico em `DECISIONS.md`.
4. Commits convencionais, ≥ 1 por fase. Nunca commitar `.env`, artefatos.
5. Só reportar números medidos pelos comandos da §10.
6. Dependência nova fora do pyproject inicial (fastapi, uvicorn, pydantic, httpx, pytest, ruff, mypy, openapi-spec-validator, pyyaml) → justificar em `DECISIONS.md`. **Não** adicionar LangGraph — o grafo aqui é simples (pipeline linear + fan-out), implementável em Python puro; o baseline usa LangGraph mas este serviço não precisa da dependência.
7. **HITL golden tem armadilha** (§12.7): frase nominal ("contas a pagar") não é escrita; leitura nunca pausa.
8. Downstreams via adapter + FakeClient; nenhum gate exige serviço no ar. Guardrails é **fail-closed** (fora → recusa, não segue aberto).
9. **traceparent** (W3C) propagado a todos os downstream (§8.3); G7 verifica.
10. Teste de SSRF-permitido usa IP literal público (template §8.5).
11. **Não tocar:** nada fora deste repo.

## 13. Riscos

| Risco | Prob. | Impacto | Mitigação |
|-------|-------|---------|-----------|
| Guardrails fora → fluxo segue sem análise (falha aberta) | M | **A** | Fail-closed explícito: guardrails fora = 503, NUNCA segue; G4 cobre |
| Fan-out parcial trava a síntese | M | M | Agente que falha marca domínio faltante; síntese usa os que responderam; deadline |
| Write intent com falso-negativo (escrita não pausa) | M | A | Léxico determinístico + golden com casos reais; HITL_ENABLED só religa o gate |
| Armadilha: "contas a pagar" pausa por engano | M | M | Frase nominal excluída (léxico exige verbo imperativo + objeto); G3 |
| Circuit breaker contando 4xx | M | M | Só transporte conta (reusa padrão svc-inference); testado |
| Complexidade do grafo (integração de 4 serviços) | M | A | Pipeline linear + fan-out em Python puro; FakeClients isolam a lógica; é o maior serviço mas sem LangGraph |

## 14. Definição de DONE

- [x] G1–G8 PASS na mesma execução; log em `evals/results/`
- [x] `docker compose up` (ecossistema) + smoke (opcional; `make smoke` + tests/test_smoke_ecosystem.py prontos): `/v1/chat` multi-domínio produz eventos route→agent→final
- [x] README: como rodar/testar, **diagrama do fluxo**, tabela de gates com números medidos, exemplo chat + resume
- [x] `DECISIONS.md` com desvios (D1–D9); `BACKLOG.md` (histórico longo, spans OTel, LangGraph se algum dia necessário)
- [x] Zero secrets/artefatos no git
- [x] Entrada em `../RETRO.md` (rodada 7 — ENCERRAMENTO): retrospectiva final do programa SDD (7/7). O método entregou? custo total? o template está pronto para reuso em outros ecossistemas?

## 15. As-built (reconciliação pós-implementação — 2026-07-07)

> Confronto da spec congelada com o que foi de fato construído. Desvios detalhados em
> `DECISIONS.md` (D1–D9); itens adiados em `BACKLOG.md`. **Status: DONE — G1–G8 PASS.**

### 15.1 Gates medidos (`make gates`, mesma execução)

| Gate | Threshold | Medido |
|------|-----------|--------|
| G1 testes | 100% pass, ≥55 | **66 passed** (+3 skipped: smoke opcional) |
| G2 fluxo | ordem correta, single/multi, block corta | **9/9 PASS** |
| G3 HITL | escrita pausa; leitura/armadilha não; resume | **12/12 PASS** (armadilha "contas a pagar" não pausa) |
| G4 SSE | route→agent→final; falha → `error`; guardrails fail-closed | **6/6 PASS** |
| G5 lint+tipos | 0 erros | ruff limpo; mypy 0 erros (9 arquivos) |
| G6 contrato | OpenAPI válido; toda rota testada | OK; 5 rotas exercitadas (test_contract.py, 7 testes) |
| G7 security+trace | fail-closed, 401, SSRF, traceparent | PASS (test_security.py, 17 testes) |
| G8 overhead | P95 < 50 ms | **P50 1.63 ms / P95 1.93 ms** (n=200, fakes, single) |

### 15.2 Ajustes em relação à spec congelada

| Item da spec | As-built | Ref |
|--------------|----------|-----|
| §5.3 fluxo: HITL como passo 4 (pós fan-out) | HITL **entre route e fan-out** (`sanitize → route → HITL → fan-out → fan-in`), coerente com §4 | D1 |
| §7 config | + `CIRCUIT_RESET_S` (default 30) | D2 |
| §8.4 downstream fora → 503 no passo | 503 para guardrails/router; **falha no fan-out/fan-in degrada** (placeholder por domínio / combinado bruto) | D3 |
| §7/§8.4 deadline global → 504 | **não implementado no v1**; teto prático = `DOWNSTREAM_TIMEOUT_S` por chamada; 504 reservado no contrato | D4, BACKLOG |
| §7 `OTEL_ENABLED` → OTLP | no-op; telemetria = /metrics + logs + traceparent W3C | D5, BACKLOG |
| §11 F0 "CI" | sem workflow de CI (padrão do ecossistema; gates via `make gates`) | D6 |
| §5.2 eventos SSE | + evento terminal `done: [DONE]` | D7 |
| §5.4 `422 {error, detail, rule}` | 422 = validação FastAPI `{detail: array}`; `BusinessError` removido do contrato | D8 |
| §12.4 ≥1 commit por fase | 1 commit inicial consolidado (convenção svc-rag) | D9 |

### 15.3 Implementado conforme especificado (destaques)

- Guardrails **fail-closed** (fora → 503, nunca segue sem análise); RAG opcional (fora/`RAG_ENABLED=0` → agente segue sem contexto).
- Circuit breaker por downstream: 3 falhas de transporte → OPEN; **4xx não conta**; OPEN → 503 sem bater no downstream; `/health` expõe o estado dos 4 breakers.
- `traceparent` W3C propagado aos 4 downstream (gerado quando ausente) — validado no G7.
- Sem LangGraph (regra §12.6): saga em Python puro (`orchestrator.py`, ~180 linhas).
- Auth interna fail-closed, `ALLOW_OPEN_ACCESS` dev-only, rate-limit por IP, SSRF guard nas URLs de downstream, Swagger off, 500 sem stack, eviction de threads (`MAX_THREADS`).
