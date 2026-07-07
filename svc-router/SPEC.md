# SPEC — svc-router v1.0

> Quarta spec do programa SDD (rodada 4). Derivada de `../SPEC_TEMPLATE.md` calibrado por RETRO rodadas 1–3. Contrato único entre arquiteto e loop de agentes.

---

## 0. Metadados

| Campo | Valor |
|-------|-------|
| Serviço | `svc-router` |
| Versão da spec | 1.0.0 |
| Status | **frozen** |
| Baseline de referência | AI-Orchestrator `fe3adc1` — `gateway/router.py`, `gateway/semantic_router.py`, `gateway/bm25.py` (RRF), `docs/golden_routing_criteria.md` |
| Repo alvo | `~/Documentos/projeto-portifolio/microservicos-ai-orchestrator/svc-router` |
| Data de congelamento | 2026-07-06 |

## 1. Contexto e problema

O coração do AI-Orchestrator é decidir **qual(is) domínio(s)** uma pergunta ativa (finanças/RH/estoque/vendas), com roteamento em **3 camadas**: (1) **semântica** — embedding da query vs. exemplares de cada rota, com recuperação **híbrida densa + BM25 fundida por RRF**; (2) **guards léxicos determinísticos** — regras que adicionam/forçam domínios (ex.: "comissão" → vendas+finanças); (3) **fallback LLM** — quando a semântica não passa do threshold, um LLM classifica nos domínios permitidos. Vive em `router.py`/`semantic_router.py`/`bm25.py`, medido em **94.1%** no golden de 153 (após auditoria de labels, `golden_routing_criteria.md`).

Este serviço extrai o roteador para uma **API independente**: recebe uma query + um conjunto de rotas (com exemplares) e devolve um **RoutePlan** (`{domains, layer, scores}`). É o primeiro serviço que **consome outros do ecossistema**: usa `svc-inference` (fachada OpenAI-compat, rodada 3) para a camada LLM. Consumidores previstos: `svc-orchestrator` (decide fan-out), apps que precisam classificar intenção.

Padrão herdado (template §8.5): a camada LLM é um **adapter atrás de interface** com **fake determinístico** — gates não exigem svc-inference no ar. A camada semântica usa **SBERT local** (mesmo embedder do svc-guardrails); o gate de acurácia carrega o modelo (gate **lento**), os demais são determinísticos (rápidos).

Lição institucionalizada: o golden de roteamento carrega **armadilhas** (uso legítimo de palavra-gatilho) e **não é ajustável** para passar gate (§12.7).

## 2. Objetivo (uma frase)

Expor roteamento de intenção em 3 camadas (semântica híbrida BM25+RRF → guards léxicos → fallback LLM) como API stateless que devolve RoutePlan rastreável (`layer` + scores), reproduzindo o padrão de decisão do AIO sobre rotas configuráveis, testável offline via embedder e LLM fake.

## 3. Não-objetivos (o agente NÃO constrói)

- Executar a intenção roteada — svc-router só decide domínios; execução é do orchestrator/serviços de domínio.
- Servir LLM — a camada LLM fala com `svc-inference` via HTTP (adapter); não hospeda modelo de geração.
- RAG / busca de documentos — isso é `svc-rag`.
- Sanitização / injection / OOD — isso é `svc-guardrails` (roda antes, no orchestrator).
- Treino de classificador supervisionado — roteamento é semântico + regras, não modelo treinado.
- UI.
- Gerenciar histórico de conversa / estado multi-turno.

## 4. Glossário

| Termo | Definição neste contexto |
|-------|--------------------------|
| Rota (domínio) | Categoria de destino (ex.: finanças); tem exemplares e, opcionalmente, guards |
| Exemplar | Frase representativa de uma rota, usada na camada semântica |
| RoutePlan | Saída: `{domains: [str], layer: str, scores: {rota: float}}` |
| Camada (`layer`) | Qual mecanismo decidiu: `semantic` \| `lexical` \| `llm` \| `fallback` |
| Híbrido denso+BM25 | Combinação de similaridade de embedding (denso) e BM25 (léxico) |
| RRF | Reciprocal Rank Fusion: funde dois rankings por `1/(k+rank)` |
| Guard léxico | Regra determinística (regex) que adiciona/força domínio(s) |
| Threshold | Score semântico mínimo para decidir sem cair no LLM |
| Armadilha | Caso do golden onde palavra-gatilho aparece em uso legítimo (anti-FP) |

## 5. Contrato de API

> Fonte da verdade: `api/openapi.yaml` (OpenAPI 3.1), gerado na F1, validado com `openapi-spec-validator`. Rotas `/v1/`.

### 5.1 Endpoints

| Método | Rota | Auth | Descrição | Erros |
|--------|------|------|-----------|-------|
| POST | `/v1/route` | interna | Roteia uma query; retorna RoutePlan (`domains`, `layer`, `scores`) | 401, 422, 503 (camada LLM exigida e adapter fora) |
| GET | `/v1/routes` | interna | Lista rotas registradas (nome + nº de exemplares + guards) | 401 |
| GET | `/health` | nenhuma | Liveness + readiness (deps: embedder, llm_adapter) | — |
| GET | `/metrics` | interna | Contadores por camada + latências; `source: live` | 401 |

### 5.2 Schemas principais (Pydantic v2 espelha o OpenAPI)

```yaml
RouteRequest:
  query: str                       # 1..MAX_QUERY_CHARS
  allow_llm: bool = true           # permite fallback LLM
  top_k: int = 3
  routes_override: list[RouteDef] | null   # usa rotas inline em vez das registradas

RouteDef:
  name: str
  exemplars: list[str]

RoutePlan:
  domains: list[str]               # 1+ domínios decididos
  layer: "semantic" | "lexical" | "llm" | "fallback"
  scores: dict[str, float]         # score por rota (semântico fundido)
  llm_used: bool

Erro de negócio: 422 {error, detail, rule}
Erro interno: 500 genérico — stack só em log.
```

### 5.3 Política de decisão (ordem determinística)
1. **Semântica híbrida**: embed query, funde denso+BM25 por RRF; se `top_score ≥ THRESHOLD` → `layer=semantic`, domínio = argmax (+ empates dentro de `TIE_MARGIN`).
2. **Guards léxicos**: sempre aplicados; **adicionam** domínios ao resultado (podem promover single→multi). Se um guard dispara e a semântica não decidiu, `layer=lexical`.
3. **Fallback LLM**: se semântica < threshold e nenhum guard decidiu e `allow_llm` → classifica via adapter; `layer=llm`. Adapter fora → `503` (ou `layer=fallback` para o argmax semântico se `LLM_FALLBACK_SOFT=1`).

### 5.4 Contrato de erro
- Negócio: `422 {error, detail, rule}`. LLM exigido e adapter fora (sem soft): `503`.
- Interno: `500` genérico; stack só em log.

## 6. Modelo de dados e estado

- **Lógica stateless.** Sem banco.
- **Rotas registradas** em código (`src/router_svc/routes.py`): nome + exemplares + guards. Podem ser sobrescritas por request (`routes_override`).
- **Índice semântico**: embeddings dos exemplares computados **no boot** (carga do SBERT no boot, lazy proibido — template §8.5) e mantidos em memória; BM25 construído sobre os exemplares. Sem artefato persistido (rotas vêm do código/request). Degradação: embedder fora → camada semântica indisponível, cai para guards + LLM; `/health` degraded.
- Isolamento de artefatos (template §6): N/A — não persiste artefatos servidos por API.

## 7. Configuração (env — 12-factor)

| Variável | Default | Obrigatória | Efeito |
|----------|---------|-------------|--------|
| `INTERNAL_KEY` | — | sim (prod) | Auth interna; ausente → 401 (fail-closed) |
| `ALLOW_OPEN_ACCESS` | `0` | não | `1` libera sem key (dev; warning no boot) |
| `EMBED_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | não | SBERT local (mesmo do svc-guardrails) |
| `ROUTE_THRESHOLD` | `0.45` | não | Score semântico mínimo p/ decidir sem LLM |
| `TIE_MARGIN` | `0.05` | não | Margem p/ empate → multi-domínio |
| `RRF_K` | `60` | não | Constante do Reciprocal Rank Fusion |
| `HYBRID_ENABLED` | `1` | não | `0` = só denso (sem BM25/RRF) |
| `LLM_ENABLED` | `0` | não | `1` liga a camada LLM (adapter HTTP) |
| `LLM_URL` | — | se LLM_ENABLED | Endpoint OpenAI-compat (svc-inference) |
| `LLM_MODEL` | — | se LLM_ENABLED | Modelo p/ classificação |
| `LLM_FALLBACK_SOFT` | `0` | não | `1` = adapter fora usa argmax semântico (`layer=fallback`) em vez de 503 |
| `MAX_QUERY_CHARS` | `2000` | não | 422 acima disso |
| `RATE_LIMIT_PER_MIN` | `120` | não | Sliding window por IP |
| `OTEL_ENABLED` | `0` | não | OTLP → Collector; fora = no-op |
| `LOG_LEVEL` | `INFO` | não | Log JSON estruturado |

> Fail-closed na segurança; degradação graceful na telemetria, no embedder e no LLM.

## 8. NFRs

### 8.1 Segurança
- Transversais (ARCHITECTURE §3.1): `hmac.compare_digest`, fail-closed, Swagger off, `.dockerignore`, `.env` fora do git.
- `LLM_URL` é config de operador (não do request), mas validar esquema http/https + bloquear metadata/loopback (anti-SSRF) no boot, salvo `ALLOW_LOCAL_LLM=1`.
- Query é dado não confiável: nunca em log sem escape, nunca ecoada em erro; guards são regex sem backtracking catastrófico.

### 8.2 Performance
- `/v1/route` **sem LLM** (semântica + guards, embedder quente): **P95 < 60 ms** em CPU (embedding domina).
- Camada LLM: latência do adapter — medida e reportada, não gateada.

### 8.3 Observabilidade
- Log JSON por rota: `{trace_id, layer, domains, top_score, llm_used, latency_ms}` — sem a query completa (preview opt-in).
- `/metrics`: `routes_total`, `by_layer{semantic,lexical,llm,fallback}`, `latency_p50/p95`; `source: live`.
- Camada LLM, se usada, propaga trace ao adapter (`traceparent`); spans OTel se `OTEL_ENABLED=1`.

### 8.4 Resiliência
- Embedder fora no boot → serviço sobe; camada semântica off; guards + LLM seguem; `/health` degraded.
- LLM adapter fora → `503` (ou soft-fallback semântico se `LLM_FALLBACK_SOFT=1`); circuito no adapter (reusar padrão do svc-inference: falha de transporte conta, 4xx não).
- Deadline por request; degradação explícita, nunca crash.

## 9. Dependências

| Dependência | Tipo | Runtime obrigatória? | Se ausente |
|-------------|------|----------------------|------------|
| sentence-transformers (local) | lib | não (camada semântica) | semântica off; guards+LLM seguem |
| svc-inference / endpoint OpenAI-compat | serviço | não (só camada LLM com `LLM_ENABLED=1`) | 503 ou soft-fallback |
| OTel Collector | infra | não | no-op |
| **Nenhum banco** | — | — | — |

> Gates: acurácia (G2) usa SBERT real (gate **lento**); demais usam **FakeEmbedder** + **FakeLLM** determinísticos (rápidos, offline).

## 10. Gates de aceitação

> Velocidade: G2 é **lento** (carrega SBERT); os demais **rápidos**. `make gates` roda todos; no loop, rodar rápidos a cada iteração e G2 ao fim/background.

| # | Gate | Velocidade | Comando | Threshold | Baseline AIO |
|---|------|-----------|---------|-----------|--------------|
| G1 | Testes | rápido | `python -m pytest -q` | 100% pass, ≥ 50 testes | — |
| G2 | Acurácia de roteamento (SBERT real) | lento | `python evals/eval_routing.py` | **≥ 0.85** no golden multi-domínio | 94.1% (golden 153) |
| G3 | Fusão RRF + camadas (determinístico) | rápido | `python evals/eval_fusion.py` | RRF bate cálculo à mão; seleção de camada correta; 0 divergência | RRF do AIO |
| G4 | Guards léxicos + armadilha | rápido | `python evals/eval_guards.py` | guards disparam certo; **armadilha não dispara** (uso legítimo) | — |
| G5 | Lint + tipos | rápido | `ruff check . && python -m mypy src/` | 0 erros | — |
| G6 | Contrato | rápido | `openapi-spec-validator api/openapi.yaml && python -m pytest tests/test_contract.py` | 0 violações; toda rota testada | — |
| G7 | Security | rápido | `python -m pytest tests/test_security.py` | fail-closed, 401, SSRF do LLM_URL bloqueado, stack não vaza | auditoria 0 |
| G8 | Perf (sem LLM) | rápido¹ | `python evals/bench_latency.py` | P95 < 60 ms (FakeEmbedder) | — |

¹ Bench usa FakeEmbedder para medir só o overhead de roteamento (fusão/guards), não o custo do SBERT.

**Dogfood (o agente constrói em F2–F4):**
- *FakeEmbedder determinístico* (hash → vetor estável, como no svc-guardrails) para gates rápidos.
- *golden de roteamento* (≥ 30 casos, 4 domínios estilo AIO + casos multi-domínio): usado no G2 com SBERT real.
- *eval_fusion*: RRF com rankings conhecidos → posição fundida calculada à mão; seleção de camada por threshold.
- *eval_guards*: cada guard com caso positivo + **armadilha** (ex.: "ignore os pedidos cancelados" não é guard de nada; "custo" que é produto e não finanças).

## 11. Plano de fases

| Fase | Entregável | Verificação | Stop condition |
|------|-----------|-------------|----------------|
| F0 | Scaffold no diretório final: repo, pyproject, Dockerfile (SBERT no build), Makefile (`python -m`), CI, SPEC.md | `docker build .` + `make check` | build verde |
| F1 | `api/openapi.yaml` + schemas Pydantic (RouteRequest/RoutePlan/RouteDef) | G6 | contrato validado |
| F2 | BM25 + RRF + embedder (Fake+SBERT) + fusão híbrida + testes | G1 subset + G3 + G5 | fusão correta |
| F3 | Guards léxicos + camadas (semantic/lexical) + `eval_guards.py` + `eval_fusion.py` | G3 + G4 | guards + armadilha PASS |
| F4 | Camada LLM (adapter HTTP + FakeLLM) + política de decisão completa + golden + `eval_routing.py` | G2 (SBERT) | acurácia ≥ 0.85 |
| F5 | API completa (`/v1/route`, `/v1/routes`) + auth + SSRF + rate-limit | G6 + G7 | security PASS |
| F6 | `/health` + `/metrics` (by_layer) + OTel opt-in + logs | smoke via compose | telemetria ok |
| F7 | Bench + README (gates medidos) + DECISIONS.md | **G1–G8 todos na mesma execução** | **DONE** |

## 12. Regras para o agente

1. Escopo = esta spec. Fora → `BACKLOG.md`.
2. Contradição/gate impossível → PARAR e perguntar.
3. Mesmo gate falhando após 3 correções distintas → parar, diagnóstico em `DECISIONS.md`.
4. Commits convencionais, ≥ 1 por fase. Nunca commitar `.env`, modelos, artefatos.
5. Só reportar números medidos pelos comandos da §10.
6. Dependência nova fora do pyproject inicial (fastapi, uvicorn, pydantic, httpx, sentence-transformers, numpy, pytest, ruff, mypy, openapi-spec-validator, pyyaml) → justificar em `DECISIONS.md`.
7. **Golden com armadilha obrigatória** (§12.7 do template): guard que não deve disparar em uso legítimo da palavra-gatilho.
8. Camada LLM é adapter + FakeLLM; nenhum gate exige svc-inference no ar. G2 usa SBERT real (lento) — aceitável.
9. **Não tocar:** nada fora deste repo.

## 13. Riscos

| Risco | Prob. | Impacto | Mitigação |
|-------|-------|---------|-----------|
| Acurácia G2 < 0.85 com golden pequeno/sintético | M | M | Golden ≥ 30 com exemplares fortes; threshold 0.85 (abaixo do 94.1% do AIO, que tinha golden auditado grande); se falhar, reforçar exemplares antes de mexer no método |
| RRF implementado errado (off-by-one no rank) | M | A | G3 com rankings conhecidos e resultado à mão; ranks começam em 1 |
| Guard regex catastrófico / falso-positivo | M | M | Guards ancorados a contexto (não palavra solta); armadilha no G4 |
| SSRF via LLM_URL | B | A | Validação de esquema + bloqueio metadata/loopback no boot; teste no G7 |
| Acoplar a svc-inference quebra ordem/gates | B | A | Adapter OpenAI-compat genérico + FakeLLM; off por default; gates offline |

## 14. Definição de DONE

- [ ] G1–G8 PASS na mesma execução; log em `evals/results/`
- [ ] `docker compose up` + smoke (`/v1/route` decide domínio via semântica; guard promove multi-domínio)
- [ ] README: como rodar/testar, tabela de gates com números medidos, exemplo de request + RoutePlan
- [ ] `DECISIONS.md` com desvios; `BACKLOG.md` com fora-de-escopo
- [ ] Zero secrets/artefatos no git
- [ ] Entrada em `../RETRO.md` (rodada 4): padrões do template bastaram? novas fricções?
