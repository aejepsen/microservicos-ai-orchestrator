# SPEC — svc-evals v1.0

> Segunda spec do programa SDD (rodada 2). Derivada de `../SPEC_TEMPLATE.md` já calibrado pela retrospectiva do piloto (`../RETRO.md`). Contrato único entre arquiteto e loop de agentes: se não está aqui, o agente não faz.

---

## 0. Metadados

| Campo | Valor |
|-------|-------|
| Serviço | `svc-evals` |
| Versão da spec | 1.0.0 |
| Status | **frozen** |
| Baseline de referência | AI-Orchestrator `fe3adc1` — `evals/eval_domains.py`, `eval_semiose.py`, `eval_faithfulness.py`, `eval_docs.py`, `gateway/eval_results.py` (EvalResultsCollector), `docs/golden_routing_criteria.md` |
| Repo alvo | `~/Documentos/projeto-portifolio/microservicos-ai-orchestrator/svc-evals` |
| Data de congelamento | 2026-07-06 |

## 1. Contexto e problema

No AI-Orchestrator, avaliação virou disciplina central: cada feature declara um **gate numérico** (`Recall@3 ≥ 80%`, `routing ≥ 90%`, `faithfulness ≥ 90%`), roda um golden set e o número decide se entra em produção. Isso vive espalhado em `evals/*.py` (um script por métrica) + o endpoint `GET /eval-results` (`eval_results.py`), que agrega resultados de `evals/results/*.json` e rotula cada métrica com a **fonte** (`live` = traces reais, `eval` = golden com data, `estimate`).

Este serviço extrai esse padrão para um **motor de avaliação reutilizável**: carrega golden sets (JSONL), aplica **scorers** plugáveis, computa métricas com **gates** (threshold + comparador → PASS/FAIL), persiste o resultado como artefato versionável e expõe os agregados por API com rótulo de fonte. É a peça que, nas rodadas seguintes, valida os demais serviços do ecossistema — por isso é o **#2 na ordem de construção** (ARCHITECTURE §4): depois do piloto, antes de inference/router/rag.

Consumidores previstos: CI dos outros `svc-*` (gate de merge), o próprio arquiteto (rodadas de medição), e `svc-observability` (que consome os resultados rotulados). O julgamento por LLM (faithfulness) é suportado como **adapter opcional** — svc-evals não serve modelo (isso é `svc-inference`, rodada 3), então o judge fala HTTP com um endpoint OpenAI-compatível e fica **desligado por default**.

Lição do piloto institucionalizada aqui: **golden carrega armadilhas** (casos que parecem o oposto do que são) e **não é ajustável para passar gate** (§12.7 do template).

## 2. Objetivo (uma frase)

Expor um motor de avaliação por golden-set como API stateless (+ artefatos de resultado), com gates numéricos machine-checkable, scorers plugáveis e rótulo de fonte (`live`/`eval`/`estimate`) por métrica, reproduzindo os gates medidos do AIO (Recall@3, routing accuracy, faithfulness) sobre entrada equivalente.

## 3. Não-objetivos (o agente NÃO constrói)

- Substituir pytest/CI — svc-evals é chamado *pela* CI, não a substitui.
- Hospedar os golden sets dos outros serviços — cada serviço traz o seu; svc-evals **consome** goldens enviados/apontados.
- UI/dashboard — visualização é responsabilidade de `svc-observability`.
- Servir ou hospedar LLM — julgamento por LLM é via **adapter HTTP** a endpoint externo (off por default).
- Treino, fine-tuning ou geração de golden — svc-evals avalia, não gera dados.
- Orquestração multi-serviço — não decide fluxo; roda a suite que lhe passam.
- Persistência relacional / histórico consultável rico — resultados são artefatos JSON append-only + agregação em memória com cache.

## 4. Glossário

| Termo | Definição neste contexto |
|-------|--------------------------|
| Golden set | Arquivo JSONL de casos rotulados; cada linha = um caso com entrada + resultado esperado |
| Scorer | Função pura `(caso, resposta_obtida) -> {passed, score}`; built-in ou registrada |
| Suite | Conjunto (golden + scorer + métrica + gate) identificado por nome |
| Métrica | Agregação dos scores dos casos (accuracy, F1, recall@k, taxa) |
| Gate | `(métrica, comparador, threshold)` → PASS/FAIL |
| Fonte (`source`) | Origem do número: `live` (dado real/traces), `eval` (golden, com data), `estimate` |
| Modo offline | Resposta já está no golden (`response`) — scorer avalia direto |
| Modo live | svc-evals chama o endpoint HTTP do serviço-alvo para obter a resposta |
| Judge adapter | Cliente HTTP opcional para LLM-juiz (OpenAI-compatível); `temperature=0`, `format=json` |
| Armadilha | Caso do golden que parece o oposto do rótulo (anti-falso-positivo/negativo) |

## 5. Contrato de API

> Fonte da verdade: `api/openapi.yaml` (OpenAPI 3.1), gerado na F1 e validado com `openapi-spec-validator`. Rotas `/v1/`.

### 5.1 Endpoints

| Método | Rota | Auth | Descrição | Erros |
|--------|------|------|-----------|-------|
| POST | `/v1/run` | interna | Roda uma suite (golden + scorer + gate); persiste artefato; retorna resultado + PASS/FAIL | 401, 422 (suite/golden inválido), 424 (modo live e alvo fora), 503 (judge exigido e adapter off) |
| GET | `/v1/suites` | interna | Lista suites registradas (nome, scorer, métrica, gate) | 401 |
| GET | `/v1/results` | interna | Agregado das últimas rodadas por suite, cada métrica com `source` + data. Cache curto | 401 |
| GET | `/v1/results/{suite}` | interna | Última rodada de uma suite (detalhe por caso opcional via `?detail=1`) | 401, 404 |
| GET | `/health` | nenhuma | Liveness + readiness (deps: judge_adapter, results_dir) | — |
| GET | `/metrics` | interna | Contadores (runs, gates_pass, gates_fail, latências) com `source: live` | 401 |

### 5.2 Schemas principais (Pydantic v2 espelha o OpenAPI)

```yaml
GateSpec:
  metric: str                 # ex. "accuracy", "recall_at_k", "faithfulness_rate"
  comparator: ">=" | ">" | "<=" | "<" | "=="
  threshold: float

RunRequest:
  suite: str                  # nome de suite registrada, OU definição inline abaixo
  golden_inline: list[object] | null   # casos JSONL inline (alternativa a suite registrada)
  scorer: str | null          # id do scorer built-in (se não vier da suite)
  scorer_params: object       # ex. {"k": 3} para recall_at_k
  gate: GateSpec | null
  mode: "offline" | "live"    # default offline
  target:                     # obrigatório se mode=live
    url: str | null
    method: str               # default POST
    input_field: str          # campo do caso enviado ao alvo
    output_pointer: str       # JSONPath simples p/ extrair a resposta

RunResponse:
  suite: str
  metric: str
  value: float
  gate: GateSpec | null
  passed: bool | null         # null se sem gate
  n_cases: int
  n_failed_cases: int
  source: "live" | "eval" | "estimate"
  ran_at: str                 # ISO-8601
  artifact_path: str

Erro de negócio: 422 {error, detail, rule}
Erro interno: 500 genérico — stack só em log.
```

### 5.3 Scorers built-in (mínimo)

`exact_match` · `contains` · `regex_match` · `numeric_threshold` · `classification` (accuracy + macro-F1) · `recall_at_k` (param `k`) · `llm_judge` (via adapter, opcional).

### 5.4 Contrato de erro
- Negócio: `422 {error, detail, rule}`. Alvo live fora: `424`. Judge exigido sem adapter: `503`.
- Interno: `500` genérico; stack só em log estruturado.

## 6. Modelo de dados e estado

- **Lógica stateless.** Sem banco relacional.
- **Suites registradas:** definidas em código (`src/evals_svc/suites.py`) e/ou via `RunRequest` inline. Cada suite: nome, caminho do golden, scorer + params, `GateSpec`, `source` default.
- **Golden sets:** JSONL em `evals/data/*.jsonl` (os do próprio svc-evals, para dogfood) ou enviados inline. Cada caso: `{input, expected, ...}`; casos de armadilha marcados `"trap": true`.
- **Artefatos de resultado:** `evals/results/<suite>_<timestamp>.json` (append-only, fora do git salvo os de referência). Contêm métrica, valor, gate, PASS/FAIL, `source`, data, e por-caso (para auditoria). O agregado de `GET /v1/results` é reconstruído desses arquivos + cache em memória (TTL curto, ex. 10s) — padrão `EvalResultsCollector` do AIO.
- **Golden imutável no run:** o motor nunca reescreve um golden. Regra §12.7.

## 7. Configuração (env — 12-factor)

| Variável | Default | Obrigatória | Efeito |
|----------|---------|-------------|--------|
| `INTERNAL_KEY` | — | sim (prod) | Auth interna; ausente → 401 (fail-closed) |
| `ALLOW_OPEN_ACCESS` | `0` | não | `1` libera sem key (só dev; warning no boot) |
| `RESULTS_DIR` | `evals/results` | não | Onde persistir artefatos de rodada |
| `RESULTS_CACHE_TTL_S` | `10` | não | TTL do cache de `GET /v1/results` |
| `JUDGE_ENABLED` | `0` | não | `1` liga o adapter LLM-judge |
| `JUDGE_URL` | — | se JUDGE_ENABLED | Endpoint OpenAI-compatível/Ollama do juiz |
| `JUDGE_MODEL` | — | se JUDGE_ENABLED | Modelo do juiz |
| `JUDGE_TIMEOUT_S` | `30` | não | Timeout por chamada de julgamento |
| `TARGET_DEADLINE_S` | `10` | não | Deadline por chamada no modo live |
| `RATE_LIMIT_PER_MIN` | `120` | não | Sliding window por IP (cadeia CF→X-Real→XFF→socket) |
| `OTEL_ENABLED` | `0` | não | OTLP → Collector; fora = no-op |
| `LOG_LEVEL` | `INFO` | não | Log JSON estruturado |

> Fail-closed na segurança; degradação graceful na telemetria e no judge (judge off → scorer `llm_judge` retorna erro de suite claro, nunca crash global).

## 8. NFRs

### 8.1 Segurança
- Transversais (ARCHITECTURE §3.1): `hmac.compare_digest`, fail-closed, Swagger off, `.dockerignore`, `.env` fora do git.
- Específico: **golden e resposta são dados não confiáveis** — nunca `eval()`/exec sobre conteúdo de caso; JSONPath do `output_pointer` é um subset seguro (sem execução); URL de `target`/`judge` só de allowlist de esquema (`http/https`) e sem SSRF para metadata local (bloquear `169.254.169.254`, `localhost` só se `ALLOW_LOCAL_TARGET=1`).

### 8.2 Performance
- `GET /v1/results` (agregação cacheada): **P95 < 50 ms**.
- Runner offline sobre golden de 100 casos com scorer determinístico: **P95 < 300 ms** (sem contar judge/live).
- Modo live e judge: latência dominada pelo alvo/juiz — fora do gate de perf (medir e reportar, não gatear).

### 8.3 Observabilidade
- Log JSON por run: `{trace_id, suite, metric, value, passed, n_cases, source, latency_ms}`.
- `/metrics`: `runs_total`, `gates_pass_total`, `gates_fail_total`, `latency_p50/p95`, todos `source: live`.
- Se `JUDGE_ENABLED=1`, chamadas ao juiz seguem OTel GenAI semconv (spans `gen_ai.*`), ARCHITECTURE §3.3.

### 8.4 Resiliência
- Alvo live fora → `424` na suite (não derruba o serviço); demais suites seguem.
- Judge fora / timeout → suite com scorer `llm_judge` falha com erro claro; suites determinísticas não afetadas.
- Deadline por request; artefato só é escrito após a rodada concluir (sem resultado parcial corrompido).

### 8.5 Ferramentas e projeto
- `ruff` line-length 100 no `src/`; `per-file-ignores` de `E501` em `tests/*` e `evals/*` (herdado do template §8.5).
- **Sem modelo local** neste serviço → sem download-no-build de pesos. Judge é HTTP remoto.
- `Makefile` chama ferramentas via `python -m` (venv não-relocável). Repo criado direto no diretório final.

## 9. Dependências

| Dependência | Tipo | Runtime obrigatória? | Se ausente |
|-------------|------|----------------------|------------|
| LLM-judge (endpoint HTTP) | serviço externo | não (só scorer `llm_judge` com `JUDGE_ENABLED=1`) | scorer llm_judge falha na suite; resto ok |
| Serviço-alvo (modo live) | serviço externo | não (só `mode=live`) | 424 na suite live |
| **Nenhum LLM local, nenhum banco** | — | — | — |

> Gates G1–G7 rodam 100% offline: dogfood usa goldens sintéticos + judge **mockado** (adapter fake), sem rede.

## 10. Gates de aceitação

> Velocidade: todos **rápidos** (svc-evals não carrega modelo local). `make gates` roda todos na mesma execução.

| # | Gate | Velocidade | Comando | Threshold | Baseline AIO |
|---|------|-----------|---------|-----------|--------------|
| G1 | Testes | rápido | `python -m pytest -q` | 100% pass, ≥ 50 testes | — |
| G2 | Correção do motor de gate | rápido | `python evals/eval_engine.py` | 100% dos casos-espelho classificados certo (PASS/FAIL) | — |
| G3 | Correção dos scorers | rápido | `python evals/eval_scorers.py` | recall@k, F1, accuracy batem valores calculados à mão (0 divergência) | Recall@3 100%, routing 94.1% reproduzidos |
| G4 | Determinismo do judge (mock) | rápido | `python evals/eval_judge.py` | mesma entrada → mesmo veredito; parse robusto a JSON sujo; faithfulness 97.5% reproduzida sobre golden-espelho | 97.5% |
| G5 | Lint + tipos | rápido | `ruff check . && python -m mypy src/` | 0 erros | — |
| G6 | Contrato | rápido | `openapi-spec-validator api/openapi.yaml && python -m pytest tests/test_contract.py` | 0 violações; toda rota testada | — |
| G7 | Security | rápido | `python -m pytest tests/test_security.py` | fail-closed, 401, SSRF bloqueado, sem exec de golden, stack não vaza | auditoria 0 |
| G8 | Perf | rápido | `python evals/bench_latency.py` | `/v1/results` P95 < 50 ms; runner 100 casos P95 < 300 ms | — |

**Goldens de dogfood (o agente constrói em F3/F4):**
- *eval_engine:* casos-espelho `(métrica, comparador, threshold, valor) -> PASS/FAIL esperado`, incluindo bordas (valor == threshold em cada comparador).
- *eval_scorers:* golden pequeno com resultado calculado à mão para `recall_at_k` (k=3), `classification` (accuracy+F1 com matriz conhecida), `exact/contains/regex`. **Armadilha obrigatória**: caso onde `contains` acertaria por acaso mas o rótulo é negativo.
- *eval_judge:* adapter fake determinístico; golden faithfulness-espelho reproduzindo 97.5% (39/40) com 1 ruído conhecido; testar parse de resposta com lixo em volta do JSON.

## 11. Plano de fases

| Fase | Entregável | Verificação | Stop condition |
|------|-----------|-------------|----------------|
| F0 | Scaffold no diretório final: repo, pyproject, Dockerfile, Makefile (`python -m`), CI, SPEC.md congelada | `docker build .` + `make check` | build verde |
| F1 | `api/openapi.yaml` + schemas Pydantic (GateSpec, RunRequest/Response) | G6 (validator) | contrato validado |
| F2 | Scorers built-in + registry + testes unitários | G1 subset + G3 + G5 | scorers corretos |
| F3 | Motor de gate (comparadores, bordas) + runner offline + `eval_engine.py` | G2 | motor 100% correto |
| F4 | Judge adapter (real HTTP + fake) + scorer `llm_judge` + `eval_judge.py` | G4 | determinismo comprovado |
| F5 | API completa (`/v1/run`, `/v1/suites`, `/v1/results*`) + modo live + auth + SSRF guard + rate-limit | G6 + G7 | security PASS |
| F6 | Results store + cache + `/health` + `/metrics` + OTel opt-in + logs | smoke via compose | telemetria ok |
| F7 | Bench + README (tabela de gates com números medidos) + DECISIONS.md | **G1–G8 todos na mesma execução** | **DONE** |

## 12. Regras para o agente

1. Escopo = esta spec. Fora → `BACKLOG.md`.
2. Contradição/gate impossível → PARAR e perguntar.
3. Mesmo gate falhando após 3 correções distintas → parar, diagnóstico em `DECISIONS.md`.
4. Commits convencionais, ≥ 1 por fase. Nunca commitar `.env`, `evals/results/*` (exceto os de referência), artefatos.
5. Só reportar números medidos pelos comandos da §10.
6. Dependência nova fora do pyproject inicial (fastapi, uvicorn, pydantic, httpx, pytest, ruff, mypy, openapi-spec-validator, pyyaml) → justificar em `DECISIONS.md`. **Não** adicionar numpy/sklearn se não for necessário; métricas simples em stdlib.
7. **Golden não é ajustável para passar gate** (template §12.7): caso que o motor erra é bug do motor. Todo golden de dogfood inclui **armadilha**. Mudança de golden → justificativa por caso.
8. Segurança de conteúdo: nunca `eval`/`exec`/`import` dinâmico sobre golden ou resposta. JSONPath restrito. URLs de target/judge validadas contra SSRF.
9. **Não tocar:** artefatos de outros serviços; svc-evals só lê goldens que recebe.

## 13. Riscos

| Risco | Prob. | Impacto | Mitigação |
|-------|-------|---------|-----------|
| Motor de gate com erro de borda (`>=` vs `>` no threshold) | M | A | G2 testa valor == threshold em cada comparador; bordas explícitas no golden-espelho |
| SSRF via `target.url`/`judge.url` | M | A | Allowlist de esquema + bloqueio de IP de metadata/localhost (§8.1); teste em G7 |
| Scorer `llm_judge` não-determinístico | M | M | `temperature=0`, `format=json`, parse tolerante; G4 com adapter fake determinístico |
| Acoplamento indevido a svc-inference (fora de ordem) | B | A | Judge é adapter HTTP genérico OpenAI-compat, off por default; svc-evals não importa svc-inference |
| JSONPath/paryer virar vetor de exec | B | A | Subset próprio sem eval; nunca interpretar golden como código (§12.8) |

## 14. Definição de DONE

- [ ] G1–G8 PASS na mesma execução; log em `evals/results/`
- [ ] `docker compose up` + smoke (`POST /v1/run` de suite offline com gate → PASS/FAIL correto)
- [ ] README: como rodar/testar, tabela de gates com números medidos, exemplo de suite + gate
- [ ] `DECISIONS.md` com desvios; `BACKLOG.md` com fora-de-escopo
- [ ] Zero secrets/artefatos no git
- [ ] Entrada em `../RETRO.md` (rodada 2): o template calibrado sustentou a construção? novas correções?
