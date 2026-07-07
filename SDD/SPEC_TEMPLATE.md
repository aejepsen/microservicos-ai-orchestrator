# SPEC — <svc-nome> v<MAJOR.MINOR>

> **Instruções de uso do template:** substitua todo `<placeholder>`. Nenhuma seção é opcional — se não se aplica, escreva "N/A + justificativa" (força decisão explícita). Toda afirmação verificável DEVE ter comando + threshold na §10. Este documento é o contrato único entre o arquiteto (humano) e o loop de agentes: se não está na spec, o agente não faz.

---

## 0. Metadados

| Campo | Valor |
|-------|-------|
| Serviço | `<svc-nome>` |
| Versão da spec | `<semver>` — specs são versionadas; agente implementa UMA versão congelada |
| Status | draft \| frozen \| implemented \| superseded |
| Baseline de referência | AI-Orchestrator `<commit-sha>` — números medidos, não aspiracionais |
| Repo alvo | `<url ou caminho>` |
| Data de congelamento | `<AAAA-MM-DD>` |

## 1. Contexto e problema

`<3–6 parágrafos: que problema este serviço resolve, de onde vem no AIO (arquivos de origem: gateway/x.py), por que vira serviço independente, quem são os consumidores previstos.>`

## 2. Objetivo (uma frase)

`<Frase única, mensurável. Ex.: "Expor análise de segurança de texto (injection + OOD + sanitização) como API stateless com P95 < 150 ms e zero falsos-negativos no golden de injection.">`

## 3. Não-objetivos (OBRIGATÓRIO — mínimo 5)

> Anti-alucinação de escopo. O agente NÃO constrói nada desta lista, mesmo que "pareça útil".

- `<não-objetivo 1 — ex.: UI/frontend>`
- `<não-objetivo 2 — ex.: persistência de histórico>`
- `<...>`

## 4. Glossário

| Termo | Definição neste contexto |
|-------|--------------------------|
| `<termo>` | `<definição — termos ambíguos entre domínios entram aqui obrigatoriamente>` |

## 5. Contrato de API (fonte da verdade)

> OpenAPI 3.1 completo em `api/openapi.yaml` no repo do serviço — o YAML é a fonte da verdade; esta seção resume. Breaking change = MAJOR bump. O agente gera o YAML ANTES de qualquer código (Fase 1) e valida com `openapi-spec-validator`.

### 5.1 Endpoints

| Método | Rota | Auth | Descrição | Erros |
|--------|------|------|-----------|-------|
| `<POST>` | `</v1/...>` | interna/pública/nenhuma | `<o que faz>` | `<códigos + contrato de erro>` |
| GET | `/health` | nenhuma | Liveness + readiness (padrão transversal, ver ARCHITECTURE §3) | — |
| GET | `/metrics` | interna | Métricas agregadas (padrão transversal) | — |

### 5.2 Schemas (Pydantic v2 espelha o OpenAPI)

```yaml
# <schemas principais inline — request/response/erro. Erro padrão: {error, detail, rule}>
```

### 5.3 Contrato de erro

- Erros de negócio: `422 {error, detail, rule}` (padrão AIO).
- Erros internos: `500` com mensagem genérica — **stack trace nunca sai na resposta**; log completo no servidor.

## 6. Modelo de dados e estado

`<Stateless? Se stateful: schema, engine (SQLite WAL + busy_timeout=5000 é o padrão AIO), migrações, retenção. Artefatos de modelo (embeddings, thresholds calibrados): formato, onde vivem (volume, fora do git), como são gerados/regenerados.>`

> **Isolamento de artefatos (lição da rodada 2):** artefatos escritos por eval-scripts (`evals/results/eval_*.json`) e payloads servidos por uma API (`GET /v1/results` e afins) NÃO podem compartilhar o mesmo diretório sem defesa — senão o leitor da API tropeça em arquivos de schema diferente (bug real: `KeyError`). Regra: (a) todo leitor de artefatos **filtra por schema** (ignora arquivo sem as chaves obrigatórias do payload), E/OU (b) diretórios separados por tipo. Testes/bench que escrevem artefatos usam `dir` temporário isolado.

## 7. Configuração (env — 12-factor)

| Variável | Default | Obrigatória | Efeito |
|----------|---------|-------------|--------|
| `<VAR>` | `<default>` | sim/não | `<efeito — todo comportamento opt-in/opt-out tem flag aqui>` |

> Regra: default de segurança é **fail-closed**; default de observabilidade é **degradação graceful** (serviço nunca cai por telemetria fora).

## 8. Requisitos não-funcionais (NFRs)

### 8.1 Segurança (inegociável)
- Auth interna: `X-Internal-Key` + `hmac.compare_digest` (ARCHITECTURE §3.1).
- Fail-closed: sem credencial configurada → endpoints protegidos bloqueiam; modo aberto só com `ALLOW_OPEN_ACCESS=1` explícito.
- Swagger/OpenAPI desabilitado em produção (`docs_url=None`, `redoc_url=None`, `openapi_url=None`).
- `.dockerignore` cobrindo `.env`, `__pycache__`, `.git`; `.env` fora do versionamento.
- `<específicos do serviço>`

### 8.2 Performance
- `<P95 alvo por endpoint, com comando de medição na §10. Baseline AIO quando existir.>`

### 8.3 Observabilidade (desde o commit 1, não retrofit)
- OTel GenAI semconv quando houver chamada LLM (padrão `gateway/otel.py` do AIO); spans + histogramas via OTLP (ARCHITECTURE §3.3).
- Log JSON estruturado com `trace_id` propagado.
- Toda métrica exposta declara **fonte**: `live` | `eval` | `estimate`.

### 8.4 Resiliência
- `<circuit breaker, timeouts, deadline por request, comportamento sob dependência fora — degradação explícita, nunca crash.>`

### 8.5 Ferramentas e projeto (padrões herdados do piloto)
- **`ruff` line-length 100 no `src/`; `per-file-ignores` de `E501` para `tests/*` e `evals/*`** — asserts descritivos e prints de relatório de gate ficam legíveis inteiros (evita ~15 lints previsíveis por serviço). Regex longo recebe `# noqa: E501` pontual.
- **Serviço com modelo (embedder/LLM local):** download **no build do Docker** + carga **no boot** do processo (lazy loading proibido — elimina cold start no 1º request). Degradação graceful se o modelo faltar (ver §8.4). Referência: `svc-guardrails/Dockerfile` + `State.__init__`.
- **venv não é relocável:** `Makefile` invoca toda ferramenta como `.venv/bin/python -m <tool>` (não `.venv/bin/<tool>`, cujo shebang quebra se a pasta mover). Se o repo for movido após o F0, rodar `make venv` de novo.
- **Dependência externa (backend LLM, serviço-alvo, embedder remoto):** modelar como **adapter atrás de interface** + um **fake determinístico**; os gates usam o fake (100% offline); o adapter real só em `make smoke` opcional. Padrão consolidado nas rodadas 2–3 (judge do svc-evals, backend do svc-inference). Nenhum gate pode exigir infra externa no ar (§9).
- **`conftest.py` padrão silencia log ruidoso:** `logging.getLogger("httpx").setLevel(WARNING)` — TestClient loga cada request em INFO e polui a saída dos eval-scripts.
- **Enums serializados usam `StrEnum`** (py3.12), não `(str, Enum)` — idioma correto, evita `ruff UP042`, mantém `.value` string no JSON.
- **Teste de SSRF-permitido usa IP público literal** (ex.: `8.8.8.8`), **não hostname** (`example.com`) — o guard resolve host via `getaddrinfo`; ambiente de gate pode não ter DNS e o guard (corretamente) recusa o que não resolve, quebrando o teste do caso "permitido". IP literal não exige DNS. (Rodada 5.)
- **BACKLOG do template — `app = create_app()` no nível do módulo** dispara `State.__init__` (e a carga do modelo, em serviços com SBERT) no **import**. Funciona e passa gates, mas acopla import a boot. Opção futura: factory lazy. Não-bloqueante. (Rodada 6.)
- **Tracing distribuído entre serviços** (quando um serviço chama outros): propagar o header **`traceparent` (W3C)** para os downstream + incluí-lo nos logs. Decidido na rodada 7 (svc-orchestrator é o primeiro a encadear vários serviços); serviços folha (sem downstream) não precisam. Spans OTel completos → BACKLOG por serviço (ver D7 do svc-rag).

## 9. Dependências

| Dependência | Tipo | Obrigatória em runtime? | Comportamento se ausente |
|-------------|------|-------------------------|--------------------------|
| `<Qdrant/Ollama/...>` | infra/serviço | sim/não | `<no-op / erro / cache stale>` |

> Testes dos gates principais NÃO podem exigir infra externa — usar fixtures/mocks; smoke test de integração separado e opcional.

## 10. Gates de aceitação (machine-checkable — o loop só termina aqui)

> Cada gate: comando exato + threshold + baseline. O agente roda TODOS ao fim de cada fase; DONE = todos PASS na mesma execução.
>
> **Velocidade do gate (custo de iteração):** cada gate é **rápido** (determinístico, <1s: lint, tipos, contrato, testes puros, evals sem modelo) ou **lento** (carrega modelo/infra: eval com embedder, bench). Durante o loop, rodar os **rápidos a cada iteração** e os **lentos ao fim da fase** — corta iterações e custo. Os lentos podem rodar em background. `make gates` roda todos na mesma execução (prova de DONE).

| # | Gate | Velocidade | Comando | Threshold | Baseline AIO |
|---|------|-----------|---------|-----------|--------------|
| G1 | Testes determinísticos | rápido | `<python -m pytest -q>` | 100% pass | `<n testes no AIO>` |
| G2 | `<eval de qualidade>` | `<rápido/lento>` | `<python evals/eval_x.py>` | `<≥ N%>` | `<número medido>` |
| G3 | Lint + tipos | rápido | `<ruff check . && python -m mypy src/>` | 0 erros | — |
| G4 | Contrato | rápido | `<openapi-spec-validator + testes de contrato>` | 0 violações | — |
| G5 | Perf | lento | `<comando de bench>` | `<P95 < X ms>` | `<baseline>` |
| G6 | Security | rápido | `<testes fail-closed + golden injection/abuso>` | `<0 leaks>` | 0/6 no AIO |

## 11. Plano de fases para o loop de agentes

> Uma fase por iteração do loop. Cada fase tem entregável, verificação e stop condition. O agente NÃO avança com a verificação falhando; NÃO refatora fases anteriores sem gate quebrado apontando para elas.
>
> **Regra de F0 robusto (aprendida rodadas 1 e 4):**
> - Criar o repo **já no diretório final** (`microservicos-ai-orchestrator/<svc-nome>/`). Mover depois quebra shebangs do `.venv` (§8.5).
> - No scaffold, criar **TODOS os diretórios de uma vez** (`mkdir -p src/<pkg> tests evals/data evals/results models`) **antes** de qualquer `touch`/escrita — um `mkdir` faltando faz um `&&` abortar e mascara a falha.
> - Comandos de **background usam paths absolutos**: um job em background roda no **cwd default**, não no cwd do serviço; caminhos relativos vão para o lugar errado.
> - Scripts de setup terminam com o **código de saída real** (`exit "$rc"`), **nunca** com um `echo` no fim — senão o job reporta "exit 0" mesmo tendo falhado (o venv pode nunca ter sido criado e o job "passa").
> - `Makefile` chama ferramentas via `python -m` (ver §8.5).

| Fase | Entregável | Verificação (comando) | Stop condition |
|------|-----------|----------------------|----------------|
| F0 | Scaffold no diretório final: repo, pyproject, Dockerfile (download do modelo no build, se houver), Makefile (`python -m`), CI, **todos os diretórios criados de uma vez** | `<docker build + make check>` | build verde + `.venv/bin/python` existe |
| F1 | `api/openapi.yaml` completo + schemas Pydantic | G4 | contrato validado |
| F2 | `<núcleo 1>` + testes | G1 (subset) | testes do módulo verdes |
| F3 | `<núcleo 2>` + testes | G1 (subset) + G2 | gate de qualidade PASS |
| F4 | Auth + NFRs de segurança | G6 | fail-closed comprovado |
| F5 | Observabilidade + /metrics + /health | `<smoke>` | telemetria verificada |
| F6 | Evals completos + bench + docs (README do serviço) | G1–G6 todos | **DONE** |
| F7 | **Reconciliação as-built** (obrigatória, aprendida na rodada 7): confrontar a spec congelada com a implementação — marcar o checklist da §14, escrever a seção **§15 As-built** (gates medidos + tabela spec×implementado) e registrar TODO desvio em `DECISIONS.md` (mesmo os que não quebram gate: feature declarada e não entregue, env extra, ordem de passos, shape de erro). Item adiado → `BACKLOG.md` | revisão da spec inteira × código | zero desvio não-registrado |

## 12. Regras para o agente (guardrails do processo)

1. **Escopo:** implementar SOMENTE o que está nesta spec. Ideia boa fora da spec → registrar em `BACKLOG.md`, não implementar.
2. **Dúvida material** (contradição na spec, gate impossível): PARAR e perguntar. Não inventar interpretação.
3. **Loop-breaker:** mesmo gate falhando após 3 tentativas de correção distintas → parar, reportar diagnóstico.
4. **Commits:** convencionais, um por fase no mínimo; nunca commitar `.env`, artefatos de modelo ou dados.
5. **Números:** só reportar métricas efetivamente medidas pelos comandos da §10 — nunca estimar e apresentar como medido.
6. **Dependências novas** (pacotes fora da §9/pyproject inicial): exigem justificativa em `DECISIONS.md`.
7. **Golden não é ajustável para passar gate:** caso que o sistema erra é bug do sistema, não do golden. Todo golden de qualidade DEVE incluir **armadilhas** — casos que parecem o oposto do que são (ex.: uso legítimo de palavra-gatilho: "ignore os pedidos cancelados" num detector de injection). Foi o que segurou o FPR baixo no piloto. Mudança de golden exige justificativa por caso em `DECISIONS.md`.
8. **Não tocar:** `<lista de caminhos/arquivos proibidos, se houver>`.

## 13. Riscos e mitigações

| Risco | Prob. | Impacto | Mitigação |
|-------|-------|---------|-----------|
| `<risco técnico>` | `<A/M/B>` | `<A/M/B>` | `<ação concreta>` |

## 14. Definição de DONE

- [ ] G1–G6 PASS na mesma execução (log anexado em `evals/results/`)
- [ ] `docker compose up` sobe o serviço + smoke test passa
- [ ] README do serviço: como rodar, como testar, tabela de gates com números medidos
- [ ] `DECISIONS.md` com desvios da spec (se houver) justificados
- [ ] Zero secrets/artefatos no git
