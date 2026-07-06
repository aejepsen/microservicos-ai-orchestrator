# Resumo de Sessão — 2026-07-06

Registro do que foi construído. Modelo executor: **Claude Fable 5** (`claude-fable-5`).

---

## 1. Sincronização do e-book com o AI-Orchestrator

Rodada de features do AIO em **2026-07-04** (3 commits: OTel GenAI, evals com fontes live/eval/estimate, tuning Ollama) não estava refletida na documentação.

**Feito:**
- `AI-Orchestrator/ebook-llm-on-premise/` — cap21 (subseção OTel GenAI: semconv, Collector fan-out Phoenix/Prometheus, tokens na fonte, fontes live/eval/estimate) + cap18 (caso medido de tuning Ollama: `NUM_PARALLEL=3` + `FLASH_ATTENTION=1`, makespan 23.3s→19.5s, −16%). Commit `e053f5d`, pushed.
- Clone externo `ebook-llm-on-premise/` sincronizado por `git pull --ff-only` (os dois diretórios são clones do mesmo repo GitHub — sync é push/pull, nunca `cp`).
- `AI-Orchestrator/README.md` + `ROADMAP.md` atualizados p/ a rodada 07-04. Commit `fe3adc1`, pushed.

---

## 2. Programa SDD — microsserviços por agentes em loop

Decisão de adotar **spec-driven development (SDD) + loop de agentes**, tomando o AI-Orchestrator como base arquitetural. Objetivo: decompor as capacidades do AIO em **7 microsserviços independentes**, construíveis do zero por agentes e integráveis em projetos futuros (contract-first).

**Pasta central criada:** `microservicos-ai-orchestrator/`

### 2.1 Método (`SDD/`)
- `README.md` — fluxo piloto → calibrar template → escalar.
- `SPEC_TEMPLATE.md` — template canônico, 14 seções, gates **machine-checkable** (comando + threshold).
- `ARCHITECTURE.md` — os 7 serviços, contratos transversais (auth `X-Internal-Key`/hmac, OTel GenAI, `/health`, `/metrics`, SemVer, repo padrão), ordem de construção.
- `specs/spec-svc-guardrails.md` — spec do piloto, **frozen v1.0.0**.
- `RETRO.md` — retrospectiva do piloto.

### 2.2 Os 7 serviços (ordem de construção)
1. **svc-guardrails** (piloto) — injection + OOD + sanitização
2. svc-evals — golden sets, gates, juiz LLM
3. svc-inference — serving LLM local (Ollama/LoRA)
4. svc-router — roteamento 3 camadas + BM25/RRF
5. svc-rag — ingestão, Qdrant, GraphRAG
6. svc-observability — OTel GenAI, métricas
7. svc-orchestrator — grafo fan-out/fan-in, HITL, SSE

**Regra do programa:** nenhuma spec nova antes do piloto passar todos os gates. O piloto calibra o template; erro de template × 7 é caro.

---

## 3. Piloto svc-guardrails — CONCLUÍDO (DONE)

Serviço stateless, zero LLM, zero banco. Extrai as defesas validadas do AIO (`security.py`, `subspace_guard.py`, nó sanitize). Repo `svc-guardrails/`, commit `230b164`.

### Gates (G1–G8, mesma execução via `make gates`)

| Gate | Métrica | Resultado | Threshold | Baseline AIO |
|------|---------|-----------|-----------|--------------|
| G1 | Testes | 125 pass | 100%, ≥60 | 410 (AIO todo) |
| G2 | Injection FN | 0/36 | 0 FN, ≥30 | 0/6 |
| G3 | Injection FPR | 0.0% (0/63) | ≤5%, ≥60 | — |
| G4 | OOD AUC (LOO) | 0.9992 | ≥0.95 | 0.9803 |
| G5 | Lint+tipos | ruff+mypy limpos | 0 erros | — |
| G6 | Contrato | OpenAPI válido | 0 violações | — |
| G7 | Security | fail-closed OK | ver tests | auditoria 0 |
| G8 | Perf P95 | 6.3 ms | <150 ms (CPU) | — |

### Arquitetura do serviço
- **Sanitização** (`sanitize.py`): controle/zero-width/delimitadores de chat.
- **Injection** (`patterns_pt.py` + `injection.py`): 12 famílias PT-BR determinísticas; roda sobre texto original; anti-FP por contexto (imperativo + objeto-instrução).
- **OOD guard** (`ood.py`): resíduo de subespaço SVD; threshold calibrado por LOO + Youden (0.817 no corpus piloto — não herdado do AIO); AUC por Mann-Whitney (sem sklearn).
- **Segurança** (`security.py`): auth interna `hmac.compare_digest` fail-closed, rate-limit por IP real, Swagger off, `.env`/modelos fora do git.
- **API** (`app.py`): `/v1/analyze`, `/v1/ood/fit`, `/v1/ood/status`, `/health`, `/metrics`; degradação graceful (embedder fora → checks ood `null`).

### Contrato
`api/openapi.yaml` (OpenAPI 3.1) é a fonte da verdade; Pydantic v2 espelha.

---

## 4. Retrospectiva — 5 correções pro template antes da rodada 2

Método **aprovado para escala**. Correções a aplicar em `SPEC_TEMPLATE.md`:
1. Nota anti-mover-repo + tools via `python -m` (venv não é relocável).
2. Classificar gates em rápido (determinístico) vs lento (exige modelo); rodar rápidos a cada iteração.
3. Template já traz `per-file-ignores` de E501 para tests/evals.
4. Padrão download-no-build + carga-no-boot para serviços com modelo.
5. Exemplo de "armadilha benigna" nos goldens (uso legítimo de palavra-gatilho).

---

## 5. Commits da sessão

| Repo | Commit | Descrição |
|------|--------|-----------|
| AI-Orchestrator | `fe3adc1` | docs: README/ROADMAP rodada 07-04 |
| ebook-llm-on-premise | `e053f5d` | docs: cap18/cap21 sync 07-04 (pushed) |
| svc-guardrails | `76b3e71` | feat(f0-f2): scaffold + núcleo |
| svc-guardrails | `230b164` | feat: piloto DONE — G1–G8 PASS |

---

## 6. Próximo passo

Rodada 2: aplicar as 5 correções do RETRO ao template, depois gerar `spec-svc-evals` (ordem em `SDD/ARCHITECTURE.md` §4).
