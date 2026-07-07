# SPEC — svc-guardrails v1.0

> Spec piloto do programa SDD. Derivada de `../SPEC_TEMPLATE.md`. Contrato único entre arquiteto e loop de agentes: se não está aqui, o agente não faz.

---

## 0. Metadados

| Campo | Valor |
|-------|-------|
| Serviço | `svc-guardrails` |
| Versão da spec | 1.0.0 |
| Status | **frozen** |
| Baseline de referência | AI-Orchestrator `fe3adc1` (2026-07-06) — `gateway/security.py`, `gateway/subspace_guard.py`, nó sanitize, `evals/` |
| Repo alvo | `~/Documentos/projeto-portifolio/svc-guardrails` (git init no F0) |
| Data de congelamento | 2026-07-06 |

## 1. Contexto e problema

Todo sistema LLM exposto a usuários precisa de 3 defesas antes do texto chegar ao modelo: (a) **sanitização** de entrada; (b) **detecção de prompt injection** (instruções adversárias embutidas: "ignore as instruções anteriores", "agora você é...", falsa autoridade); (c) **detecção de out-of-distribution** — pergunta fora do domínio do sistema, que não deve ser respondida com confiança.

No AI-Orchestrator essas defesas vivem acopladas ao gateway (`security.py`, `subspace_guard.py`, nó `sanitize` do grafo) e foram validadas em produção: **0/6 vazamentos** no golden de injection, **OOD guard com AUC 0.9803** (protocolo leave-one-out, threshold 0.48), auditoria com **0 achados CRITICO/ALTO/MEDIO**.

Este serviço extrai essas defesas para uma **API stateless independente**, consumível por qualquer projeto futuro (svc-orchestrator, apps novos) sem carregar o resto do gateway. É também o **piloto do método SDD**: valida template + loop de agentes antes das outras 6 specs.

Duas lições do AIO que esta spec institucionaliza: (1) o fit do subespaço OOD deve **excluir casos de clarification** — são fora-de-domínio por design e contaminam o subespaço; (2) calibração de threshold **exige LOO** — split 80/20 superestimou o threshold no AIO.

## 2. Objetivo (uma frase)

Expor análise de segurança de texto (sanitização + injection + OOD) como API stateless com P95 < 150 ms (CPU), zero falsos-negativos no golden adversarial de injection e AUC ≥ 0.95 no golden OOD.

## 3. Não-objetivos (o agente NÃO constrói)

- UI/frontend de qualquer tipo.
- Rate-limit-as-a-service (rate-limit existe apenas como middleware protegendo ESTE serviço).
- Defesa em camada de prompt (regras de system prompt são responsabilidade do consumidor).
- Moderação de conteúdo (toxicidade, PII, temas sensíveis) — só injection + OOD + sanitização.
- Persistência de histórico de análises (stateless; logs estruturados bastam).
- Chamadas a LLM — serviço 100% determinístico + embeddings locais; zero dependência de Ollama.
- Multi-idioma além de PT-BR (léxicos e goldens são PT-BR; EN é trabalho futuro).
- Auto-retreino / fit automático do subespaço (fit é operação administrativa explícita).

## 4. Glossário

| Termo | Definição neste contexto |
|-------|--------------------------|
| Injection | Texto contendo instrução adversária destinada a alterar o comportamento do LLM consumidor |
| OOD | Out-of-distribution: entrada semanticamente distante do corpus in-domain fitado |
| Resíduo de subespaço | Norma da componente do embedding ortogonal ao subespaço SVD do corpus in-domain |
| LOO | Leave-one-out: protocolo de calibração do threshold OOD (obrigatório; 80/20 proibido) |
| Verdict | Resultado por checagem: `{flagged: bool, score, evidence}` |
| Decision | Agregação dos verdicts: `allow` \| `flag` \| `block` conforme política configurável |
| Fail-closed | Sem credencial configurada → endpoint protegido responde 401/403, nunca abre |

## 5. Contrato de API

> Fonte da verdade: `api/openapi.yaml` (OpenAPI 3.1), gerado na Fase F1 e validado com `openapi-spec-validator`. Rotas prefixadas `/v1/`.

### 5.1 Endpoints

| Método | Rota | Auth | Descrição | Erros |
|--------|------|------|-----------|-------|
| POST | `/v1/analyze` | interna | Analisa texto: sanitização + injection + OOD; retorna verdicts + decision | 401, 413 (texto > `MAX_TEXT_CHARS`), 422, 503 (OOD exigido sem artefato fitado) |
| POST | `/v1/ood/fit` | interna | Fita subespaço a partir de corpus enviado; persiste artefato + calibra threshold LOO | 401, 422 (corpus < 30 amostras), 409 (fit em andamento) |
| GET | `/v1/ood/status` | interna | Metadados do artefato ativo: n_amostras, threshold, data, hash do corpus | 401 |
| GET | `/health` | nenhuma | `{status, version, deps: {embedder: ok\|down, ood_artifact: ok\|absent}}` | — |
| GET | `/metrics` | interna | Contadores agregados (analyses, blocks, flags, latências) com campo `source` | 401 |

### 5.2 Schemas principais

```yaml
AnalyzeRequest:
  text: str            # obrigatório, 1..MAX_TEXT_CHARS
  checks: list[str]    # default ["sanitize","injection","ood"]; subconjunto permitido
  context: str | null  # rótulo do chamador p/ logs (ex.: "svc-orchestrator")

AnalyzeResponse:
  sanitized_text: str
  verdicts:
    injection: {flagged: bool, score: float, patterns: list[str]}   # patterns = ids das regras disparadas
    ood: {flagged: bool, residual: float, threshold: float} | null  # null se check não pedido/artefato ausente
  decision: "allow" | "flag" | "block"
  latency_ms: float

Erro de negócio: 422 {error, detail, rule}
Erro interno: 500 genérico — stack trace só em log estruturado.
```

### 5.3 Política de decisão (determinística, configurável)

- `injection.flagged` → `block` (sempre; inegociável).
- `ood.flagged` → `OOD_ACTION` (`flag` default — espelha o modo log-only do AIO; `block` opt-in).
- Nenhum flag → `allow`.

## 6. Modelo de dados e estado

- **Serviço stateless.** Nenhum banco.
- **Artefato OOD** (`models/ood_subspace.npz` + `models/ood_meta.json`): componentes SVD, média, threshold LOO, hash e tamanho do corpus, timestamp. Vive em volume, **fora do git**. Ausência de artefato → check `ood` responde `null` + `deps.ood_artifact: absent` no /health (degradação declarada, não erro — exceto se `OOD_REQUIRED=1` → 503).
- **Regra de fit (lição AIO):** corpus de fit deve vir já filtrado pelo chamador; a API rejeita amostras marcadas `is_clarification: true` se o campo vier presente. Threshold SEMPRE via LOO sobre o corpus de fit + conjunto OOD de calibração fornecido no request.
- **Léxico de injection**: `src/guardrails/patterns_pt.py` — regras versionadas em código (id, regex, descrição, exemplos). Mínimo 12 famílias cobrindo: ignore-instruções, redefinição de persona ("agora você é"), falsa autoridade ("como administrador ordeno"), exfiltração de prompt ("repita suas instruções"), delimitadores adversários, payload encoding óbvio (base64 de comando), instrução para omitir/violar regras, jailbreak clássico PT.

## 7. Configuração (env — 12-factor)

| Variável | Default | Obrigatória | Efeito |
|----------|---------|-------------|--------|
| `INTERNAL_KEY` | — | sim (prod) | Auth interna; ausente → endpoints internos 401 (fail-closed) |
| `ALLOW_OPEN_ACCESS` | `0` | não | `1` libera sem key (só dev; logar warning no boot) |
| `EMBED_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | não | SBERT local (mesmo do AIO) |
| `OOD_ACTION` | `flag` | não | `flag` \| `block` |
| `OOD_REQUIRED` | `0` | não | `1` → /v1/analyze com check ood e artefato ausente = 503 |
| `MAX_TEXT_CHARS` | `8000` | não | 413 acima disso |
| `RATE_LIMIT_PER_MIN` | `120` | não | Sliding window por IP (cadeia CF-Connecting-IP → X-Real-IP → XFF → socket; `max_entries=10000` + eviction) |
| `OTEL_ENABLED` | `0` | não | OTLP → Collector; fora do ar = no-op |
| `LOG_LEVEL` | `INFO` | não | Log JSON estruturado |

## 8. NFRs

### 8.1 Segurança
- Todos os itens transversais (ARCHITECTURE §3.1): `hmac.compare_digest`, fail-closed, Swagger off em prod, `.dockerignore`, `.env` fora do git.
- Específico: o próprio texto analisado é hostil por definição — nunca interpolar em logs sem escape; nunca ecoar em mensagens de erro.

### 8.2 Performance
- `/v1/analyze` (3 checks, texto ≤ 1000 chars): **P95 < 150 ms** em CPU (embedding MiniLM domina). Sem OOD: P95 < 20 ms.
- Embedder carregado no boot (lazy loading proibido — evita cold start no primeiro request).

### 8.3 Observabilidade
- Log JSON por análise: `{trace_id, context, decision, injection.patterns, ood.residual, latency_ms}` — **sem o texto completo** (privacy; primeiro 80 chars com escape, opt-in via `LOG_TEXT_PREVIEW=1`).
- `/metrics`: `analyses_total`, `blocks_total`, `flags_total`, `latency_p50/p95`, todos `source: live`.
- Sem chamadas LLM → GenAI semconv N/A; spans HTTP comuns via OTel se `OTEL_ENABLED=1`.

### 8.4 Resiliência
- Embedder falhou no boot → serviço sobe, `/health` reporta `embedder: down`, checks `ood` retornam `null` (degradação declarada); `sanitize`+`injection` (determinísticos) continuam.
- Request deadline 10 s.

## 9. Dependências

| Dependência | Tipo | Runtime obrigatória? | Se ausente |
|-------------|------|----------------------|------------|
| sentence-transformers (local) | lib | não (só check ood) | ood → null |
| OTel Collector | infra | não | no-op |
| **Nenhum serviço externo, nenhum LLM, nenhum banco** | — | — | — |

Gates G1–G7 rodam 100% offline (modelo SBERT baixado no build do Docker / cache local).

## 10. Gates de aceitação

| # | Gate | Comando | Threshold | Baseline AIO |
|---|------|---------|-----------|--------------|
| G1 | Testes | `pytest -q` | 100% pass, ≥ 60 testes | 410 no AIO inteiro |
| G2 | Injection adversarial | `python evals/eval_injection.py` | **0 falsos-negativos** em ≥ 30 casos adversariais | 0/6 |
| G3 | Injection benigno (FPR) | idem (mesmo script, seção benign) | FPR ≤ 5% em ≥ 60 casos benignos PT | — |
| G4 | OOD | `python evals/eval_ood.py` | **AUC ≥ 0.95** (protocolo LOO) em golden ≥ 30 in / ≥ 30 out | AUC 0.9803, 27/30 @ 0.48 |
| G5 | Lint+tipos | `ruff check . && mypy src/` | 0 erros | — |
| G6 | Contrato | `python -m openapi_spec_validator api/openapi.yaml && pytest tests/test_contract.py` | 0 violações; toda rota do YAML tem teste | — |
| G7 | Security | `pytest tests/test_security.py` | fail-closed (sem key → 401), 413, stack não vaza, rate-limit dispara | auditoria 0 achados |
| G8 | Perf | `python evals/bench_latency.py` | P95 < 150 ms (analyze completo, CPU) | — |

**Goldens (o agente constrói em F3/F4, com critérios):**
- *Injection adversarial (≥30):* expandir as 6 famílias canônicas do AIO (ignore-instruções, redefinição de persona, falsa autoridade + variantes) cobrindo as 12 famílias da §6; cada caso com `family_id` e justificativa de 1 linha.
- *Benigno (≥60):* perguntas de negócio PT-BR legítimas, incluindo armadilhas ("ignore os pedidos cancelados no relatório" — uso legítimo de "ignore").
- *OOD:* in-domain = corpus de negócio (finanças/RH/estoque/vendas, estilo golden AIO); out = temas alheios (receitas, esporte, código, filosofia). Goldens versionados em `evals/data/*.jsonl`.

## 11. Plano de fases

| Fase | Entregável | Verificação | Stop condition |
|------|-----------|-------------|----------------|
| F0 | Scaffold (ARCHITECTURE §3.5): repo git, pyproject, Dockerfile, compose, CI local (`make check`), SPEC.md congelada | `docker build .` + `make check` | build verde |
| F1 | `api/openapi.yaml` completo + schemas Pydantic espelhando | G6 (validator) | contrato validado |
| F2 | Sanitização + léxico injection (12 famílias) + testes unitários | G1 subset + G5 | módulos verdes |
| F3 | Goldens injection (adversarial+benigno) + `eval_injection.py` | G2 + G3 | 0 FN, FPR ≤ 5% |
| F4 | OOD guard (SVD residual + fit LOO + artefato) + golden + `eval_ood.py` | G4 | AUC ≥ 0.95 |
| F5 | API completa (`/v1/analyze`, `/v1/ood/*`), auth fail-closed, rate-limit, deadline | G6 + G7 | security PASS |
| F6 | `/health`, `/metrics`, OTel opt-in, logs estruturados | smoke via compose | telemetria ok |
| F7 | Bench + README (tabela de gates com números medidos) + DECISIONS.md | **G1–G8 todos na mesma execução** | **DONE** |

## 12. Regras para o agente

1. Escopo = esta spec. Ideia fora → `BACKLOG.md`, não implementar.
2. Contradição na spec ou gate impossível → PARAR e perguntar. Não inventar.
3. Mesmo gate falhando após 3 correções distintas → parar, reportar diagnóstico em `DECISIONS.md`.
4. Commits convencionais, ≥ 1 por fase. Nunca commitar `.env`, `models/*`, resultados brutos grandes.
5. Só reportar números efetivamente medidos pelos comandos da §10.
6. Dependência nova fora do pyproject inicial (fastapi, pydantic, sentence-transformers, numpy, pytest, ruff, mypy, openapi-spec-validator) → justificar em `DECISIONS.md`.
7. Golden não é ajustável para passar gate: caso adversarial que o detector erra é bug do detector, não do golden. Mudança de golden exige justificativa por caso em `DECISIONS.md`.
8. Threshold OOD calibrado só via LOO — hardcode do 0.48 do AIO é proibido (corpus é outro).

## 13. Riscos

| Risco | Prob. | Impacto | Mitigação |
|-------|-------|---------|-----------|
| Léxico regex frágil (FN em paráfrases adversariais) | M | A | Famílias com variantes morfológicas; G2 com 0 FN força cobertura; casos novos entram no golden, nunca saem |
| FPR alto (bloquear uso legítimo de "ignore", "esqueça") | M | M | Golden benigno com armadilhas (G3); regras exigem contexto imperativo+objeto-instrução, não palavra solta |
| AUC < 0.95 com corpus sintético pequeno | M | M | Corpus in-domain ≥ 100 amostras; se falhar, aumentar amostras antes de mexer no método (lição AIO: variância domina em n pequeno) |
| Latência do embedder estoura P95 em CPU fraca | B | M | Modelo MiniLM (mesmo do AIO); bench no gate; batch=1 sem GPU é suficiente |
| Agente "resolve" gate afrouxando golden | M | A | Regra 7 da §12 + revisão humana do diff de `evals/data/` antes do DONE |

## 14. Definição de DONE

- [ ] G1–G8 PASS na mesma execução; log em `evals/results/`
- [ ] `docker compose up` + smoke test (analyze com injection conhecida → block)
- [ ] README: como rodar/testar, tabela de gates com números medidos, exemplos de request
- [ ] `DECISIONS.md` com desvios justificados; `BACKLOG.md` com ideias fora de escopo
- [ ] Zero secrets/artefatos de modelo no git
- [ ] Retrospectiva do piloto registrada em `SDD/RETRO.md` (o que travou, custo, correções de template)
