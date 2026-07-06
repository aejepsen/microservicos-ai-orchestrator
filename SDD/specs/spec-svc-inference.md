# SPEC — svc-inference v1.0

> Terceira spec do programa SDD (rodada 3). Derivada de `../SPEC_TEMPLATE.md` calibrado por RETRO rodadas 1 e 2. Contrato único entre arquiteto e loop de agentes.

---

## 0. Metadados

| Campo | Valor |
|-------|-------|
| Serviço | `svc-inference` |
| Versão da spec | 1.0.0 |
| Status | **frozen** |
| Baseline de referência | AI-Orchestrator `fe3adc1` — `gateway/llm.py` (OllamaClient, chat_stream, usage na fonte), `gateway/otel.py` (GenAI semconv, TTFT), `gateway/tools/circuit.py` (CircuitBreaker), `docker-compose.yml` (tuning Ollama) |
| Repo alvo | `~/Documentos/projeto-portifolio/microservicos-ai-orchestrator/svc-inference` |
| Data de congelamento | 2026-07-06 |

## 1. Contexto e problema

Todo serviço LLM do ecossistema precisa falar com um modelo local. No AI-Orchestrator isso vive em `gateway/llm.py`: um `OllamaClient` que faz chat (bloqueante e streaming NDJSON), lê o **usage real na fonte** (`prompt_eval_count`/`eval_count`), mede **TTFT** no streaming, e propaga tudo como spans/histogramas OTel GenAI (`gen_ai.*`). Está acoplado ao gateway.

Este serviço extrai essa camada para uma **fachada de inferência independente e OpenAI-compatível**: um endpoint estável (`/v1/chat/completions`, streaming SSE, `/v1/models`) na frente de um **backend** local (Ollama), com observabilidade GenAI, contabilização de tokens na fonte, circuit breaker e degradação graceful. Qualquer serviço futuro (svc-router, svc-orchestrator) ou o próprio svc-evals (como judge) fala com esta fachada em vez de acoplar a um vendor.

Por que fachada OpenAI-compat: é o contrato de-facto; svc-evals já tem um `HttpJudge` OpenAI-compat — svc-inference é o par natural dele. Trocar Ollama por vLLM/TGI no futuro não muda o contrato para os consumidores.

**Restrição de gates (crítica):** os gates NÃO podem exigir um Ollama no ar (ARCHITECTURE §9 / template §9). Toda a lógica é testada contra um **backend fake determinístico**; o backend Ollama real é um adapter exercido só em smoke opcional. Tuning de inferência (NUM_PARALLEL, FLASH_ATTENTION) é **documentado** (herdado do AIO, medido lá), não re-medido aqui — svc-inference não hospeda o modelo, orquestra a chamada.

## 2. Objetivo (uma frase)

Expor inferência de LLM local como fachada OpenAI-compatível (chat completions + streaming SSE + models), com usage de tokens **na fonte**, TTFT medido, spans OTel GenAI, circuit breaker e degradação graceful, testável 100% offline via backend fake.

## 3. Não-objetivos (o agente NÃO constrói)

- Servir/hospedar os pesos do modelo — isso é o Ollama/backend; svc-inference é a fachada HTTP.
- Treino, fine-tuning, quantização ou export GGUF.
- Roteamento semântico / escolha de modelo por conteúdo — isso é `svc-router`.
- RAG, embeddings ou busca — isso é `svc-rag`.
- Orquestração multi-agente / grafo — isso é `svc-orchestrator`.
- UI/playground.
- Multi-tenancy / billing.
- Re-medir tuning de hardware (NUM_PARALLEL etc.) — documentado do AIO, não é gate.

## 4. Glossário

| Termo | Definição neste contexto |
|-------|--------------------------|
| Backend | Provedor de inferência real (Ollama) atrás da fachada; adapter plugável |
| Fachada | API OpenAI-compatível estável exposta ao ecossistema |
| Usage na fonte | Tokens lidos do backend (`prompt_eval_count`/`eval_count`), não estimados |
| TTFT | Time-to-first-token no streaming — a latência que o usuário sente |
| GenAI semconv | OpenTelemetry Semantic Conventions para LLM (`gen_ai.*`) |
| Circuit breaker | 3 falhas de transporte → OPEN 30s → half-open; 4xx não conta (padrão AIO) |
| FakeBackend | Backend determinístico para gates: resposta e usage previsíveis, sem rede |

## 5. Contrato de API

> Fonte da verdade: `api/openapi.yaml` (OpenAPI 3.1), gerado na F1, validado com `openapi-spec-validator`. Rotas `/v1/` compatíveis com OpenAI onde aplicável.

### 5.1 Endpoints

| Método | Rota | Auth | Descrição | Erros |
|--------|------|------|-----------|-------|
| POST | `/v1/chat/completions` | interna | Chat completion (bloqueante ou `stream:true` → SSE). Compatível OpenAI | 401, 422, 503 (backend fora / circuito OPEN), 504 (deadline) |
| GET | `/v1/models` | interna | Lista modelos disponíveis no backend (formato OpenAI `{data:[{id,...}]}`) | 401, 503 |
| GET | `/health` | nenhuma | Liveness + readiness (deps: backend, circuit) | — |
| GET | `/metrics` | interna | Contadores + latências + tokens agregados; `source: live` | 401 |

### 5.2 Schemas principais (Pydantic v2 espelha o OpenAI subset)

```yaml
ChatMessage: {role: "system"|"user"|"assistant", content: str}
ChatCompletionRequest:
  model: str
  messages: list[ChatMessage]
  stream: bool = false
  temperature: float = 0.0
  max_tokens: int | null
ChatCompletionResponse:   # stream=false
  id: str
  object: "chat.completion"
  model: str
  choices: [{index, message: ChatMessage, finish_reason}]
  usage: {prompt_tokens, completion_tokens, total_tokens}   # NA FONTE
# stream=true: SSE de ChatCompletionChunk (object "chat.completion.chunk"),
#   delta incremental + evento final [DONE]; usage no último chunk.
Erro: 422 {error, detail, rule}; interno 500 genérico (stack só em log).
```

### 5.3 Contrato de erro
- Negócio: `422 {error, detail, rule}`. Backend fora / circuito OPEN: `503`. Deadline: `504`.
- Interno: `500` genérico; stack só em log.

## 6. Modelo de dados e estado

- **Lógica stateless** quanto a conversas — sem histórico (isso é do orchestrator). Estado de processo: circuit breaker (contadores por backend), agregados de métrica.
- **Sem artefatos de modelo no serviço** (os pesos vivem no backend Ollama). Sem banco.
- Isolamento de artefatos (template §6): N/A — svc-inference não persiste artefatos de eval servidos por API; bench usa medição em memória.

## 7. Configuração (env — 12-factor)

| Variável | Default | Obrigatória | Efeito |
|----------|---------|-------------|--------|
| `INTERNAL_KEY` | — | sim (prod) | Auth interna; ausente → 401 (fail-closed) |
| `ALLOW_OPEN_ACCESS` | `0` | não | `1` libera sem key (dev; warning no boot) |
| `BACKEND` | `ollama` | não | `ollama` \| `fake` (fake para dev/gates) |
| `BACKEND_URL` | `http://localhost:11434` | não | Endpoint do Ollama |
| `DEFAULT_MODEL` | — | não | Modelo default se request não especificar |
| `REQUEST_DEADLINE_S` | `120` | não | Deadline global por request (504 ao exceder) |
| `BACKEND_TIMEOUT_S` | `60` | não | Timeout por chamada ao backend |
| `CIRCUIT_FAIL_THRESHOLD` | `3` | não | Falhas de transporte → OPEN |
| `CIRCUIT_RESET_S` | `30` | não | Tempo em OPEN antes de half-open |
| `RATE_LIMIT_PER_MIN` | `120` | não | Sliding window por IP |
| `OTEL_ENABLED` | `0` | não | OTLP → Collector; fora = no-op |
| `LOG_LEVEL` | `INFO` | não | Log JSON estruturado |

> Fail-closed na segurança; degradação graceful na telemetria (OTel fora = no-op) e no backend (fora = 503 limpo + circuito, nunca crash).

## 8. NFRs

### 8.1 Segurança
- Transversais (ARCHITECTURE §3.1): `hmac.compare_digest`, fail-closed, Swagger off, `.dockerignore`, `.env` fora do git.
- `BACKEND_URL` é config de operador (não vem do request) → sem superfície SSRF do usuário; ainda assim validar esquema http/https no boot.
- Conteúdo de `messages` é dado não confiável: nunca interpolar em log sem escape; nunca ecoar em erro.

### 8.2 Performance
- **Overhead da fachada** (com FakeBackend, exclui tempo do modelo): **P95 < 30 ms** no `/v1/chat/completions` não-streaming.
- TTFT e latência total com backend real: **medidos e reportados** (não gateados — dependem do hardware/modelo). Baseline AIO documentado: ~2–4 s/task no LoRA 9B.

### 8.3 Observabilidade (desde o commit 1)
- **OTel GenAI semconv** (padrão `gateway/otel.py`): span por chamada com `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons`; histogramas `gen_ai.client.token.usage`, `gen_ai.client.operation.duration`, `gen_ai.server.time_to_first_token`. Opt-in `OTEL_ENABLED=1`; fora = no-op.
- **Tokens na fonte**: usage vem do backend, nunca estimado. Se o backend não reportar, `usage` reflete o que veio (0 explícito, não inventado).
- `/metrics`: `requests_total`, `tokens_input_total`, `tokens_output_total`, `ttft_ms_p50/p95`, `latency_ms_p50/p95`, `circuit_state`; todos `source: live`.
- Log JSON com `trace_id` propagado (W3C `traceparent`).

### 8.4 Resiliência
- **Circuit breaker** por backend (padrão AIO): `CIRCUIT_FAIL_THRESHOLD` falhas de transporte → OPEN por `CIRCUIT_RESET_S` → half-open (1 tentativa). 4xx do backend NÃO conta como falha de circuito. Circuito OPEN → `503` imediato (sem bater no backend).
- **Deadline** global por request → `504`. Backend timeout separado.
- Backend fora / erro de transporte → `503 {error, detail, rule}`, log completo no servidor; serviço nunca cai.
- Streaming: se o backend cair no meio, encerra o SSE com evento de erro limpo (sem travar a conexão).

## 9. Dependências

| Dependência | Tipo | Runtime obrigatória? | Se ausente |
|-------------|------|----------------------|------------|
| Ollama (backend) | serviço externo | não (`BACKEND=fake` para dev/gates) | 503 + circuito; `/health` degraded |
| OTel Collector | infra | não | no-op |
| **Nenhum banco, nenhum modelo no serviço** | — | — | — |

> Gates G1–G8 rodam com `BACKEND=fake` — 100% offline. Smoke com Ollama real é separado e opcional (`make smoke`, exige Ollama no ar).

## 10. Gates de aceitação

> Velocidade: todos **rápidos** (FakeBackend, sem modelo real). `make gates` roda todos na mesma execução.

| # | Gate | Velocidade | Comando | Threshold | Baseline AIO |
|---|------|-----------|---------|-----------|--------------|
| G1 | Testes | rápido | `python -m pytest -q` | 100% pass, ≥ 50 testes | — |
| G2 | Compat OpenAI (fake) | rápido | `python evals/eval_openai_compat.py` | shape de chat.completion + chunks de stream + `[DONE]` corretos; 0 divergência | — |
| G3 | Tokens na fonte | rápido | `python evals/eval_usage.py` | usage do backend propagado à resposta E às métricas; nunca estimado | usage na fonte (fix tokens=0 do AIO) |
| G4 | Resiliência | rápido | `python evals/eval_resilience.py` | circuito abre após N falhas; OPEN → 503 sem bater no backend; deadline → 504 | breaker 3→OPEN 30s |
| G5 | Lint + tipos | rápido | `ruff check . && python -m mypy src/` | 0 erros | — |
| G6 | Contrato | rápido | `openapi-spec-validator api/openapi.yaml && python -m pytest tests/test_contract.py` | 0 violações; toda rota testada | — |
| G7 | Security | rápido | `python -m pytest tests/test_security.py` | fail-closed, 401, stack não vaza, rate-limit | auditoria 0 |
| G8 | Perf (overhead fachada) | rápido | `python evals/bench_latency.py` | P95 < 30 ms (FakeBackend, não-stream) | — |

**Dogfood (o agente constrói em F2–F4):**
- *FakeBackend determinístico*: dado `messages`, devolve conteúdo fixo + usage previsível (ex.: `prompt_tokens=len(prompt.split())`), e um modo streaming que emite N chunks + final com usage.
- *eval_openai_compat*: valida o envelope OpenAI (bloqueante e streaming) contra o FakeBackend.
- *eval_usage*: injeta usage conhecido no FakeBackend, verifica propagação à resposta e ao `/metrics`.
- *eval_resilience*: FakeBackend configurável para falhar → prova abertura/reset do circuito e códigos 503/504. **Armadilha**: 4xx do backend NÃO deve abrir o circuito (caso que parece falha mas não conta).

## 11. Plano de fases

| Fase | Entregável | Verificação | Stop condition |
|------|-----------|-------------|----------------|
| F0 | Scaffold no diretório final: repo, pyproject, Dockerfile, Makefile (`python -m`), CI, SPEC.md congelada | `docker build .` + `make check` | build verde |
| F1 | `api/openapi.yaml` (subset OpenAI) + schemas Pydantic | G6 (validator) | contrato validado |
| F2 | Backend abstrato + FakeBackend + OllamaBackend (chat + stream, usage na fonte) + testes | G1 subset + G5 | backends verdes |
| F3 | Fachada `/v1/chat/completions` (bloqueante + SSE) + `/v1/models` + `eval_openai_compat.py` + `eval_usage.py` | G2 + G3 | compat + usage PASS |
| F4 | Circuit breaker + deadline + degradação + `eval_resilience.py` | G4 | resiliência PASS |
| F5 | Auth fail-closed + rate-limit + NFRs de segurança | G6 + G7 | security PASS |
| F6 | OTel GenAI semconv + `/health` + `/metrics` + logs | smoke via compose | telemetria ok |
| F7 | Bench + README (gates medidos) + DECISIONS.md + `make smoke` (Ollama opcional) | **G1–G8 todos na mesma execução** | **DONE** |

## 12. Regras para o agente

1. Escopo = esta spec. Fora → `BACKLOG.md`.
2. Contradição/gate impossível → PARAR e perguntar.
3. Mesmo gate falhando após 3 correções distintas → parar, diagnóstico em `DECISIONS.md`.
4. Commits convencionais, ≥ 1 por fase. Nunca commitar `.env`, artefatos.
5. Só reportar números medidos pelos comandos da §10. Tuning de hardware do AIO é citado como referência documentada, nunca apresentado como medido aqui.
6. Dependência nova fora do pyproject inicial (fastapi, uvicorn, pydantic, httpx, pytest, ruff, mypy, openapi-spec-validator, pyyaml) → justificar em `DECISIONS.md`.
7. **Golden/dogfood com armadilha obrigatória** (template §12.7): incluir o caso 4xx-não-abre-circuito.
8. Nenhum gate pode exigir Ollama no ar — `BACKEND=fake` nos gates; Ollama só no `make smoke` opcional.
9. **Não tocar:** nada fora deste repo.

## 13. Riscos

| Risco | Prob. | Impacto | Mitigação |
|-------|-------|---------|-----------|
| Divergência do envelope OpenAI (campo faltando) | M | M | G2 valida shape bloqueante e streaming contra fixture; `object`/`finish_reason`/`usage` obrigatórios |
| Streaming SSE com usage no lugar errado | M | M | Contrato fixa usage no último chunk antes de `[DONE]`; testado no G2 |
| Circuit breaker contando 4xx como falha | M | A | Armadilha explícita no G4; só erro de transporte conta |
| Acoplamento a Ollama vazando no contrato | B | A | Fachada OpenAI-compat; backend atrás de interface; troca de vendor não muda API |
| Gate exigir modelo real por engano | B | A | Regra §12.8 + FakeBackend default nos gates |

## 14. Definição de DONE

- [ ] G1–G8 PASS na mesma execução; log em `evals/results/`
- [ ] `docker compose up` + smoke (`/v1/chat/completions` com FakeBackend → envelope OpenAI válido; stream idem)
- [ ] README: como rodar/testar, tabela de gates com números medidos, exemplo de request (bloqueante + stream)
- [ ] `DECISIONS.md` com desvios; `BACKLOG.md` com fora-de-escopo
- [ ] Zero secrets/artefatos no git
- [ ] Entrada em `../RETRO.md` (rodada 3): a correção de results_dir bastou? novas fricções?
