# DEFERRED_SPECS — Implementações Futuras Recuperadas (v2)

| Campo | Valor |
|---|---|
| Documento | SDD/DEFERRED_SPECS.md |
| Status | REGISTRADO (specs candidatas — não congeladas) |
| Origem | BACKLOG.md + DECISIONS.md dos 7 serviços (rodadas 1–7) |
| Data | 2026-07-07 |
| Relacionado | SDD/NEXT_PHASES.md (fases 8–25), SDD/ARCHITECTURE.md |

> Este documento recupera e consolida **tudo que foi explicitamente adiado** durante as 7 rodadas SDD — itens que ficaram registrados como "implementação futura" nos BACKLOG.md e como reduções de escopo nos DECISIONS.md. Cada item vira uma spec candidata com origem rastreável, contrato proposto e gates de aceitação. Quando uma spec for promovida, ela deve ser congelada em `SDD/specs/` seguindo o SPEC_TEMPLATE.

---

## Índice de specs candidatas

| ID | Tema | Serviços afetados | Origem | Prioridade |
|---|---|---|---|---|
| DS-01 | OTel real (exporter OTLP + spans HTTP) | svc-router, svc-rag, svc-orchestrator, svc-observability | D6 (router), D7 (rag), D5 (orch), D1 (obs) + BACKLOGs | Alta |
| DS-02 | Persistência SQLite/Postgres — histórico de evals | svc-evals | BACKLOG evals ("banco relacional de rodadas") | Alta |
| DS-03 | Persistência SQLite/Postgres — histórico de conversa | svc-orchestrator | BACKLOG orch ("histórico de longo prazo em banco") | Alta |
| DS-04 | Deadline global por request (504) | svc-orchestrator | DECISIONS D4 + BACKLOG orch | Média |
| DS-05 | CI de ecossistema | todos | DECISIONS orch D6 | Alta (= FASE 10) |
| DS-06 | Backends reais de inferência (vLLM/TGI) + roteamento por modelo | svc-inference | BACKLOG inference | Média |
| DS-07 | Batching/fila + cache de respostas | svc-inference | BACKLOG inference | Média |
| DS-08 | Re-ranking LLM nível 2 + multi-query expansion | svc-router, svc-rag | BACKLOGs router/rag | Média |
| DS-09 | Guardrails EN + moderação de conteúdo (PII/toxicidade) | svc-guardrails | BACKLOG guardrails | Média |
| DS-10 | Rate-limit-as-a-service (/v1/gate) | svc-guardrails | BACKLOG guardrails | Baixa |
| DS-11 | Alerting/paging + TSDB de longo prazo | svc-observability | BACKLOG observability | Média |
| DS-12 | Registro dinâmico de upstreams | svc-observability | BACKLOG observability | Baixa |
| DS-13 | Conectores de fonte (Drive/S3/crawler) | svc-rag | BACKLOG rag | Baixa |
| DS-14 | Comunidades Louvain offline | svc-rag | BACKLOG rag | Baixa |
| DS-15 | Aprendizado de exemplares por feedback | svc-router | BACKLOG router | Baixa |
| DS-16 | HITL no nível da tool call + LangGraph | svc-orchestrator | BACKLOG orch | Média |
| DS-17 | UI/dashboard de evals + geração automática de goldens | svc-evals | BACKLOG evals | Baixa |

---

## DS-01 — OTel real: exporter OTLP + spans HTTP próprios — ✅ RESOLVIDA (FASE 12, 2026-07-07; as-built NEXT_PHASES §12.4)

**Origem exata:**
- svc-router DECISIONS **D6**: `OTEL_ENABLED` existe mas é no-op (sem exporter real).
- svc-rag DECISIONS **D7**: idem — observabilidade v1 via `/metrics` + logs JSON + propagação `traceparent` W3C apenas.
- svc-orchestrator DECISIONS **D5**: exporter OTLP real adiado; BACKLOG: "spans OTel HTTP próprios".
- svc-observability DECISIONS **D1**: o serviço é um agregador (pull/scrape), **não** um Collector OTLP — collector real é infraestrutura.

**Motivação:** hoje o trace distribuído existe apenas como propagação de `traceparent` em logs JSON. Sem spans reais não há visualização de latência por hop, nem correlação visual da cadeia orchestrator → router → rag → inference → guardrails.

**Contrato proposto:**
1. Dependências: `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-httpx`.
2. Config por env (todas os serviços): `OTEL_ENABLED` (default `0`), `OTEL_EXPORTER_OTLP_ENDPOINT` (default `http://localhost:4318`), `OTEL_SERVICE_NAME` (default = nome do serviço), `OTEL_TRACES_SAMPLER_ARG` (default `1.0`).
3. Com `OTEL_ENABLED=0`: comportamento idêntico ao atual (no-op, zero overhead, gates offline intactos).
4. Com `OTEL_ENABLED=1`: span de servidor por request (auto-instrument FastAPI) + span de cliente por chamada downstream (httpx), com atributos `service.name`, `http.route`, `http.status_code` e IDs consistentes com o `traceparent` já propagado.
5. Collector OTLP: sobe como infra no docker-compose da FASE 12 (Jaeger all-in-one recebe OTLP em 4318).

**Gates de aceitação:**
- G-OTEL-1: com `OTEL_ENABLED=0`, todos os gates G1–G8 atuais permanecem PASS sem alteração (regressão zero).
- G-OTEL-2: com `OTEL_ENABLED=1` + Jaeger no ar, um `POST /v1/chat` no orchestrator produz um trace único com spans dos 5+ serviços encadeados (parent-child correto).
- G-OTEL-3: `trace_id` no log JSON == `trace_id` do span exportado.
- G-OTEL-4: overhead de P95 com OTel ligado ≤ +20% vs baseline do G8.

**Dependências:** FASE 12 (Jaeger/Prometheus/Grafana). **Estimativa:** 1 rodada (afeta 5 repos, mas padrão idêntico — módulo `otel.py` compartilhável por template).

---

## DS-02 — Persistência de histórico de evals (SQLite dev / Postgres prod)

**Origem exata:** svc-evals BACKLOG — "histórico consultável rico (banco relacional de rodadas)". Hoje o `ResultsStore` grava arquivos em `evals/results/` (file-based, sem consulta agregada).

**Motivação:** comparar rodadas ao longo do tempo (regressão de qualidade), filtrar por suíte/serviço/tag, alimentar o futuro dashboard (DS-17).

**Contrato proposto:**
1. Camada `ResultsRepository` (port) com duas implementações: `FileResultsRepository` (atual, default — mantém gates offline) e `SqlResultsRepository` (SQLAlchemy 2.x + Alembic).
2. Config: `EVALS_DB_URL` (default vazio → file-based; `sqlite:///evals.db` dev; `postgresql+psycopg://...` prod).
3. Schema mínimo: `runs(id, suite, service, started_at, finished_at, git_sha, config_json)`, `cases(id, run_id FK, case_name, verdict, score, latency_ms, details_json)`; índices em `(suite, started_at)` e `(run_id, verdict)`.
4. Novos endpoints: `GET /v1/runs?suite=&service=&limit=`, `GET /v1/runs/{id}`, `GET /v1/runs/compare?a=&b=` (diff de veredictos por caso).
5. Migração: comando `python -m evals.migrate_results` importa os arquivos existentes de `evals/results/` para o banco (idempotente).

**Gates de aceitação:**
- G-DB-1: com `EVALS_DB_URL` vazio, todos os gates atuais PASS (file-based intacto).
- G-DB-2: suíte de testes do repositório SQL roda 100% offline com SQLite in-memory.
- G-DB-3: `compare` detecta corretamente um caso que passou em A e falhou em B (golden com armadilha).
- G-DB-4: importador é idempotente (rodar 2× não duplica runs).

**Dependências:** nenhuma (SQLite não requer infra). Postgres entra via docker-compose na FASE 9. **Estimativa:** 1 rodada.

---

## DS-03 — Persistência de conversa de longo prazo (svc-orchestrator)

**Origem exata:** svc-orchestrator BACKLOG — "histórico de conversa de longo prazo (banco)". Hoje o checkpoint por `thread_id` é **in-memory** (perde-se no restart; não escala horizontalmente).

**Motivação:** durabilidade de threads entre restarts, múltiplas réplicas do orchestrator, auditoria de conversas (junto com HITL).

**Contrato proposto:**
1. Port `CheckpointStore` com implementações: `MemoryCheckpointStore` (atual, default), `SqliteCheckpointStore` (dev, arquivo local) e `PostgresCheckpointStore` (prod).
2. Config: `CHECKPOINT_DB_URL` (default vazio → memória).
3. Schema: `threads(thread_id PK, created_at, updated_at, metadata_json)`, `messages(id, thread_id FK, seq, role, content_json, created_at)`, `pending_confirmations(thread_id FK, action_json, expires_at)`; índice `(thread_id, seq)`.
4. Semântica preservada: mesma API de checkpoint usada pelo grafo atual — troca de backend não muda contrato HTTP.
5. Retenção: `THREAD_TTL_DAYS` (default 30) com purga preguiçosa no acesso + comando de limpeza.
6. Se for adotado LangGraph (DS-16), avaliar `langgraph-checkpoint-sqlite`/`-postgres` oficiais em vez de implementação própria.

**Gates de aceitação:**
- G-CKPT-1: com backend memória, gates atuais PASS sem alteração.
- G-CKPT-2: golden multi-turno: enviar turno 1, **reiniciar o processo**, enviar turno 2 com mesmo `thread_id` → contexto preservado (SQLite).
- G-CKPT-3: confirmação HITL pendente sobrevive a restart e expira corretamente por `expires_at` (armadilha: confirmar após expiração → 409).
- G-CKPT-4: testes do backend Postgres rodam offline via SQLite in-memory (mesma camada SQLAlchemy) + suíte opcional com Postgres real no CI (DS-05).

**Dependências:** FASE 9 (Postgres no compose) para prod. **Estimativa:** 1 rodada.

---

## DS-04 — Deadline global por request (504)

**Origem exata:** svc-orchestrator DECISIONS **D4** — v1 usa apenas timeouts por downstream; deadline global `REQUEST_DEADLINE_S → 504` ficou no BACKLOG por exigir orquestração assíncrona/cancelamento.

**Contrato proposto:**
1. Config: `REQUEST_DEADLINE_S` (default `0` = desligado).
2. Implementação: `asyncio.timeout(deadline)` envolvendo o pipeline do `/v1/chat`; cancelamento propaga aos clientes httpx em voo.
3. Resposta: `504` com envelope de erro padrão (`code=DEADLINE_EXCEEDED`, `trace_id`), logado com o tempo decorrido por etapa.
4. Orçamento por hop (opcional v2): deadline restante propagado via header `x-deadline-ms` aos downstreams.

**Gates:** G-DL-1: `REQUEST_DEADLINE_S=0` → regressão zero. G-DL-2: fake lento (sleep > deadline) → 504 em ≤ deadline+100ms. G-DL-3: armadilha — downstream responde 1ms antes do deadline → 200 normal.

**Dependências:** nenhuma. **Estimativa:** 0,5 rodada.

---

## DS-05 — CI de ecossistema

**Origem exata:** svc-orchestrator DECISIONS **D6** — nenhum repo tem CI; adiado como preocupação de ecossistema.

**Resolução:** já especificado como **FASE 10** em `SDD/NEXT_PHASES.md` §10 (GitHub Actions: lint + testes + gates G1–G8 offline por serviço + build de imagem). Este item apenas registra a rastreabilidade D6 → FASE 10. Acrescentar à FASE 10: job opcional com Postgres de serviço para G-CKPT-4/G-DB-* quando DS-02/DS-03 existirem.

---

## DS-06 — Backends reais de inferência (vLLM/TGI) + roteamento por modelo

**Origem exata:** svc-inference BACKLOG — "backends vLLM/TGI" e "roteamento por modelo".

**Contrato proposto:**
1. Novos adapters `VllmBackend` e `TgiBackend` implementando o port `Backend` existente (mesmo padrão adapter+fake do template §8.5), falando OpenAI-compatible API (vLLM) e API nativa TGI.
2. Config: `BACKENDS_JSON` mapeando `model → {kind, base_url, api_key_env, timeout_s}`; requisição escolhe backend pelo campo `model` (fail-closed: modelo desconhecido → 400 `UNKNOWN_MODEL`).
3. Fakes determinísticos para ambos os protocolos (goldens offline, incluindo armadilhas: 429 do backend, resposta truncada, timeout).

**Gates:** G-INF-1: gates atuais PASS com fake default. G-INF-2: goldens de protocolo vLLM/TGI via fakes. G-INF-3: modelo desconhecido → 400. G-INF-4 (manual/opcional): smoke contra vLLM real em GPU.

**Estimativa:** 1 rodada.

---

## DS-07 — Batching/fila de requests + cache de respostas

**Origem exata:** svc-inference BACKLOG — "batching/fila de requests", "cache de respostas".

**Contrato proposto:**
1. **Cache**: chave = hash(model + messages + params determinísticos); só cacheia `temperature=0`; `CACHE_TTL_S` e `CACHE_MAX_ITEMS` (LRU em memória v1; Redis v2 na FASE 9). Header de resposta `x-cache: hit|miss`.
2. **Fila/batching**: fila asyncio com `MAX_CONCURRENCY` e `QUEUE_MAX` (excesso → 429 `QUEUE_FULL` com `Retry-After`); micro-batching opcional para backends que suportam (vLLM já batcheia internamente — medir antes de implementar).

**Gates:** G-CACHE-1: 2ª chamada idêntica com temp=0 → hit, latência < 5ms. G-CACHE-2: armadilha — temp>0 nunca cacheia. G-Q-1: fila cheia → 429 com Retry-After. G-Q-2: P95 sob concorrência ≤ alvo do G8.

**Dependências:** DS-06 (para valor real). **Estimativa:** 1 rodada.

---

## DS-08 — Re-ranking LLM nível 2 + multi-query expansion

**Origem exata:** svc-router BACKLOG ("re-ranking LLM nível 2", "multi-query expansion") + svc-rag BACKLOG ("re-ranking LLM nível 2").

**Contrato proposto:**
1. Port `Reranker` (nível 2) chamado após o ranking léxico/vetorial atual: envia top-K candidatos ao svc-inference com prompt de julgamento pareado/pontual; `RERANK_ENABLED=0` default.
2. `MultiQueryExpander`: gera N variações da query via LLM, une resultados por RRF (reciprocal rank fusion); `MULTIQUERY_N` (default 0 = off).
3. Fakes: `FakeReranker` determinístico (ordena por marcador no texto do golden) — gates offline.
4. Orçamento: re-ranking adiciona 1 chamada LLM → registrar latência em métrica própria `rerank_latency_ms`.

**Gates:** G-RR-1: flags off → regressão zero. G-RR-2: golden onde ranking nível 1 erra a ordem e o nível 2 corrige (armadilha incluída: nível 2 não pode piorar top-1 correto). G-MQ-1: golden de recall — doc só encontrado com expansão. G-RR-3: P95 com rerank ≤ alvo definido na promoção da spec.

**Dependências:** svc-inference disponível. **Estimativa:** 1 rodada (router + rag compartilham o padrão).

---

## DS-09 — Guardrails EN + moderação de conteúdo (PII/toxicidade)

**Origem exata:** svc-guardrails BACKLOG — "suporte EN (léxico + goldens)" e "moderação de conteúdo (PII/toxicidade)".

**Contrato proposto:**
1. **EN**: léxico paralelo `lexicon_en.json`, detecção de idioma leve (heurística ou `LANG` no request); goldens EN espelhando as armadilhas PT (falsos positivos por substring, unicode, leetspeak).
2. **PII**: detectores regex+validação (CPF com dígito verificador, e-mail, telefone BR, cartão com Luhn); ação configurável por categoria: `block | redact | flag`; resposta inclui `pii_findings[]` com spans mascarados.
3. **Toxicidade**: v1 léxico ponderado por categoria; v2 opcional via classificador no svc-inference (adapter+fake).

**Gates:** G-GRD-EN-1: goldens EN ≥ mesmo threshold dos PT. G-PII-1: CPF válido → detectado; CPF com DV inválido → NÃO (armadilha). G-PII-2: `redact` mascara sem vazar no log. G-TOX-1: goldens de toxicidade com armadilhas de contexto (citação/negação).

**Estimativa:** 1 rodada.

---

## DS-10 — Rate-limit-as-a-service (`/v1/gate`)

**Origem exata:** svc-guardrails BACKLOG — "rate-limit-as-a-service (/v1/gate)".

**Contrato proposto:** `POST /v1/gate {key, cost?}` → `{allowed, remaining, reset_at}`; token bucket por chave; backend memória v1, Redis v2; fail-closed configurável (`GATE_FAIL_MODE=closed|open`, default `closed`). Consumidores (orchestrator/inference) chamam antes de operações caras.

**Gates:** G-GATE-1: bucket esgota e recupera deterministicamente (clock fake). G-GATE-2: armadilha — chaves distintas não interferem. G-GATE-3: backend indisponível + fail-closed → negado.

**Estimativa:** 0,5 rodada.

---

## DS-11 — Alerting/paging + TSDB de longo prazo (svc-observability)

**Origem exata:** svc-observability BACKLOG — "alerting/paging", "TSDB/histórico longo".

**Resolução parcial:** a FASE 12 (NEXT_PHASES §12) cobre Prometheus+Grafana, que substituem o histórico longo e viabilizam Alertmanager. Spec candidata residual:
1. `alerts.yaml` no svc-observability: regras sobre os agregados que ele já coleta (`upstream_down`, `p95_above_threshold`, `error_rate`), avaliadas no ciclo de scrape.
2. Notificador com port `Alerter` (fake nos gates; webhook/Slack em prod).
3. Estado de alerta com histerese (`for: N ciclos`) para evitar flapping (armadilha nos goldens).
4. Decisão a tomar na promoção: manter alerting no serviço vs delegar 100% ao Alertmanager (recomendado se FASE 12 for feita — nesse caso este item vira só regras YAML do Prometheus).

**Gates:** G-AL-1: upstream derrubado por N ciclos → alerta disparado 1×. G-AL-2: armadilha — 1 ciclo ruim isolado NÃO dispara. G-AL-3: recuperação emite `resolved`.

**Dependências:** FASE 12. **Estimativa:** 0,5–1 rodada.

---

## DS-12 — Registro dinâmico de upstreams (svc-observability)

**Origem exata:** svc-observability BACKLOG — "registro dinâmico de upstreams".

**Contrato proposto:** `POST/DELETE /v1/upstreams {name, base_url}` (auth interna), persistido em arquivo/SQLite (reusar padrão DS-02); merge com a lista estática de env; validação fail-closed de URL (somente http(s), sem redirecionar para metadados de cloud — SSRF guard).

**Gates:** G-UP-1: upstream registrado passa a ser scrapeado no próximo ciclo. G-UP-2: armadilha SSRF — `http://169.254.169.254` → 400. G-UP-3: sobrevive a restart (persistência).

**Estimativa:** 0,5 rodada.

---

## DS-13 — Conectores de fonte (Drive/S3/crawler) — svc-rag

**Origem exata:** svc-rag BACKLOG — "conectores de fonte (Drive/S3/crawler)".

**Contrato proposto:** port `SourceConnector.list() / fetch(id)` com adapters `S3Connector`, `DriveConnector`, `CrawlerConnector` (reusa FakeScraper existente); pipeline de ingestão incremental por `etag/mtime` (não reprocessa inalterados); config `SOURCES_JSON`; credenciais só via env (fail-closed se ausentes).

**Gates:** G-SRC-1: ingestão incremental — 2ª rodada sem mudanças → 0 reprocessos (armadilha: mudança só de mtime sem mudança de conteúdo → hash igual, não reindexa). G-SRC-2: fakes 100% offline. G-SRC-3: credencial ausente → erro claro no startup, não em runtime.

**Estimativa:** 1 rodada.

---

## DS-14 — Comunidades Louvain offline — svc-rag

**Origem exata:** svc-rag BACKLOG — "geração offline de comunidades Louvain".

**Contrato proposto:** comando batch `python -m rag.communities` que roda Louvain (via `networkx` ou `python-louvain`) sobre o grafo de entidades já existente, gera resumos por comunidade (LLM via adapter+fake) e persiste em artefato versionado consumido pelo retrieval (padrão GraphRAG global-search). Determinismo: `seed` fixa nos gates.

**Gates:** G-LOU-1: grafo golden pequeno → partição esperada (seed fixa). G-LOU-2: query "global" que só responde bem com resumo de comunidade (golden). G-LOU-3: artefato ausente → retrieval degrada para modo atual sem erro.

**Estimativa:** 1 rodada.

---

## DS-15 — Aprendizado de exemplares por feedback — svc-router

**Origem exata:** svc-router BACKLOG — "aprendizado de exemplares por feedback".

**Contrato proposto:** `POST /v1/feedback {query, chosen_route, outcome}`; exemplares promovidos ao índice de roteamento quando `outcome=positive` acumular ≥ N ocorrências (anti-poisoning: só de chamadores autenticados, cap por rota, TTL); persistência via padrão DS-02 (SQLite).

**Gates:** G-FB-1: feedback repetido N× altera roteamento de query ambígua (golden). G-FB-2: armadilha — 1 feedback isolado NÃO altera. G-FB-3: cap impede que uma rota domine o índice.

**Dependências:** DS-02 (padrão de persistência). **Estimativa:** 1 rodada.

---

## DS-16 — HITL no nível da tool call + migração LangGraph — svc-orchestrator

**Origem exata:** svc-orchestrator BACKLOG — "confirmação no nível da tool call (interceptar POST/PUT/DELETE)" e "LangGraph (se o grafo crescer)".

**Contrato proposto:**
1. **HITL por tool call**: interceptor no executor de tools classifica por método/efeito (`GET` = safe; `POST/PUT/DELETE` = requer confirmação); pausa o grafo, retorna `202 {pending_confirmation, action_preview, confirm_token}`; `POST /v1/confirm {thread_id, confirm_token, approve}` retoma. Requer checkpoint durável (DS-03) para sobreviver a restart.
2. **LangGraph**: promover apenas se nº de nós/arestas do grafo manual ultrapassar limiar acordado (~8 nós ou necessidade de paralelismo/subgrafos). Migração mantém contrato HTTP idêntico; checkpointer = DS-03.

**Gates:** G-HITL-1: tool POST → 202 pendente; aprovar → executa 1×; negar → não executa (armadilha: replay do confirm_token → 409). G-HITL-2: GET nunca pausa. G-LG-1 (se migrar): todos os goldens atuais PASS sem mudança de contrato.

**Dependências:** DS-03. **Estimativa:** 1 rodada (HITL); +1 (LangGraph, se aprovado).

---

## DS-17 — UI/dashboard de evals + geração automática de goldens — svc-evals

**Origem exata:** svc-evals BACKLOG — "UI/dashboard" e "geração automática de golden".

**Contrato proposto:**
1. **Dashboard**: página estática servida pelo próprio svc-evals (`GET /ui`) consumindo os endpoints do DS-02 (runs, compare); sem framework pesado (HTML+JS vanilla) — tabela de rodadas, sparkline de score por suíte, diff A/B.
2. **Geração de goldens**: comando `python -m evals.suggest_goldens` que amostra tráfego real (logs) ou usa LLM (adapter+fake) para propor casos; saída em `goldens/proposed/` — **sempre revisão humana antes de promover** (goldens são contrato).

**Gates:** G-UI-1: `/ui` renderiza runs do banco (teste smoke). G-GG-1: propostas nunca entram direto na suíte oficial (diretório separado, gate falha se `proposed/` for referenciado por suíte).

**Dependências:** DS-02. **Estimativa:** 1 rodada.

---

## Mapa de rastreabilidade DECISIONS → specs

| Decisão original | Serviço | Spec que resolve |
|---|---|---|
| D6 — OTEL_ENABLED no-op | svc-router | DS-01 |
| D7 — OTEL_ENABLED no-op | svc-rag | DS-01 |
| D5 — exporter OTLP adiado | svc-orchestrator | DS-01 |
| D1 — agregador ≠ Collector OTLP | svc-observability | DS-01 (collector via FASE 12) |
| D4 — sem deadline global (504) | svc-orchestrator | DS-04 |
| D6 — sem CI em nenhum repo | svc-orchestrator | DS-05 → FASE 10 |

## Ordem de execução sugerida

1. **DS-05/FASE 10** (CI) — protege tudo que vem depois.
2. **DS-01** (OTel real) junto com **FASE 12** — maior valor de portfólio/observabilidade.
3. **DS-02 + DS-03** (persistência SQLite→Postgres) — desbloqueiam DS-15, DS-16, DS-17.
4. **DS-04** (deadline 504) — pequeno, alto valor de robustez.
5. Demais por demanda: DS-06/07 (inferência real), DS-08 (qualidade retrieval), DS-09/10 (guardrails), DS-11/12 (obs), DS-13/14 (rag), DS-16/17.

## Regras de promoção

- Cada DS-xx promovido vira `SDD/specs/spec-<slug>.md` congelada via SPEC_TEMPLATE (metadados, contratos, goldens com armadilhas, gates G1–G8).
- Regra invariável: **gates offline com fakes determinísticos**; integrações reais ficam atrás de flags default-off.
- Regressão zero: toda spec deferida deve provar que, com flags desligadas, os gates atuais dos 7 serviços permanecem PASS.
