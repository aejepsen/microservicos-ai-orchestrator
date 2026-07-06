# RETRO — Rodada 1 (piloto svc-guardrails)

Produto principal da rodada: aprendizado sobre o método SDD + agentes em loop. O serviço é subproduto (funciona; reutilizável).

## Veredito

O template guiou a construção de ponta a ponta (F0→F7) até **G1–G8 todos PASS**, sem contradição material que exigisse parar. Método validado. Correções abaixo são refinamentos, não falhas estruturais.

## Resultados do piloto

| Gate | Resultado | Baseline AIO |
|------|-----------|--------------|
| G1 testes | 125 pass | — |
| G2 injection FN | 0/36 | 0/6 |
| G3 injection FPR | 0.0% (0/63) | — |
| G4 OOD AUC (LOO) | 0.9992 | 0.9803 |
| G5 lint+mypy | limpo | — |
| G6 contrato | OpenAPI válido | — |
| G7 security | fail-closed OK | auditoria 0 |
| G8 P95 | 5.8 ms | — |

## O que travou / atritou

1. **Move quebra o venv.** Mover o repo depois de criado invalidou os shebangs dos wrappers do `.venv`. Impacto real (comando `.venv/bin/mypy` falhou). Não é problema de spec, mas de operação.
2. **Bench e OOD exigem SBERT** (~download + load). Cada gate com embedder custa segundos; rodar em background foi necessário para não bloquear o loop.
3. **E501 em asserts/prints** de teste/eval: line-length 100 gera ruído onde legibilidade pede linha inteira.
4. **Ordem dos gates importa para o loop:** gates determinísticos (G2/G3/G5/G6) dão feedback em <1s; gates com embedder (G4/G8) são lentos. Rodar os rápidos primeiro corta iterações.

## Correções a aplicar no SPEC_TEMPLATE.md (antes das 6 specs restantes)

- [x] **§11 (fases):** nota anti-move + `make venv` + tools via `python -m`. Aplicado 2026-07-06 (§8.5, §11 F0).
- [x] **§10 (gates):** coluna Velocidade rápido/lento + regra "rápidos a cada iteração, lentos ao fim da fase / background". Aplicado 2026-07-06.
- [x] **§8.3 / config:** `per-file-ignores` de E501 para tests/evals prescrito no §8.5. Aplicado 2026-07-06.
- [x] **Boot do embedder:** download-no-build + carga-no-boot + degradação graceful no §8.5. Aplicado 2026-07-06.
- [x] **Goldens:** regra de "armadilha" obrigatória vira §12.7 do template. Aplicado 2026-07-06.

**Todas as 5 correções aplicadas ao `SPEC_TEMPLATE.md` em 2026-07-06. Template calibrado — rodada 2 liberada.**

## Custo (referência para as próximas rodadas)

- Superfície: ~9 módulos src, 5 arquivos de teste, 3 evals, contrato OpenAPI.
- Gates lentos (G4/G8) dominados pelo load do SBERT, não pela lógica.
- Nenhuma intervenção humana para desbloquear lógica; única fricção foi operacional (venv/move).

## Decisão

Método **aprovado para escala**. Aplicar as 5 correções ao `SPEC_TEMPLATE.md`, depois gerar `spec-svc-evals` (rodada 2, ordem em ARCHITECTURE §4).

---

# RETRO — Rodada 2 (svc-evals)

Segundo serviço construído com o template **já calibrado**. Veredito: template sustentou a construção F0→F7 até **G1–G8 todos PASS**, sem intervenção de lógica.

## Resultados

| Gate | Resultado |
|------|-----------|
| G1 testes | 54 pass |
| G2 motor de gate | 10/10 (bordas incl.) |
| G3 scorers | 10/10 (recall@3 0.833, routing F1 1.0) |
| G4 judge determinístico | faithfulness 0.975 |
| G5 lint+mypy | limpo |
| G6 contrato | OpenAPI válido |
| G7 security | SSRF + fail-closed OK |
| G8 perf | /results P95 1.6ms, runner 0.1ms |

## O que as 5 correções do template evitaram

- Repo criado direto no diretório final → **zero problema de venv/move** (a fricção nº1 do piloto não repetiu).
- `per-file-ignores` de E501 já no pyproject → sobrou apenas lint de `src/` (8 linhas), corrigido rápido; nenhum ruído em tests/evals.
- Gates classificados: svc-evals é todo rápido (sem modelo) → loop de iteração quase instantâneo.
- Regra da "armadilha" no golden → dogfood de scorers já nasceu com casos-armadilha (contains_trap, recall fora do top-k).

## Nova fricção (rodada 2)

- **Colisão de artefatos no `results_dir`:** eval scripts e o `ResultsStore` compartilham `evals/results/`. Quebrou o G8 na 1ª execução (`KeyError: 'suite'`). Corrigido (DECISIONS D5). **Correção a levar ao template:** prescrever que artefatos de eval-script e payloads de rodada servidos pela API não compartilhem diretório, OU que todo leitor de resultados filtre por schema. Candidato a §6/§8.5 do template na próxima calibração.

## Decisão

Template robusto. **1 correção nova pendente** (isolamento de results_dir) — aplicar antes ou junto da rodada 3. Próximo: `spec-svc-inference` (rodada 3, ordem ARCHITECTURE §4).

---

# RETRO — Rodada 3 (svc-inference)

Terceiro serviço; template com a correção de results_dir (§6) já aplicada. Veredito: F0→F7 até **G1–G8 todos PASS**, sem intervenção de lógica. Primeiro serviço com **dependência externa opcional** (Ollama) — o padrão FakeBackend/adapter provou-se.

## Resultados

| Gate | Resultado |
|------|-----------|
| G1 testes | 57 pass |
| G2 compat OpenAI | 10/10 (bloqueante + stream + [DONE]) |
| G3 tokens na fonte | 7/7 (usage → resposta e /metrics) |
| G4 resiliência | 5/5 (circuito abre; 4xx não abre) |
| G5 lint+mypy | limpo |
| G6 contrato | OpenAPI válido |
| G7 security | fail-closed OK |
| G8 perf (overhead) | P95 1.9ms |

## O que funcionou (padrões que viram norma)

- **Backend fake vs real via Protocol**: gates 100% offline mesmo com o serviço existindo para falar com Ollama. É o mesmo molde do `judge` do svc-evals (fake/HTTP). Deve virar seção do template: "serviço com dependência externa → adapter + fake determinístico; gates usam fake".
- **Correção de results_dir (rodada 2) bastou**: svc-inference não persiste artefatos servidos por API; nenhuma colisão. Não surgiu fricção nova de results_dir.
- **Armadilha no golden** (4xx não abre circuito) pegou exatamente o tipo de bug sutil que a regra §12.7 existe para forçar.

## Nova fricção (rodada 3)

- **Ruído de log httpx** nos eval-scripts (TestClient loga cada request em INFO) — cosmético, resolvido com `logging.getLogger("httpx").setLevel(WARNING)` no conftest. **Candidato ao template**: conftest padrão já silencia httpx.
- **StrEnum vs (str, Enum)**: ruff UP042 no 3.12. Trivial. Vale nota no template: usar `StrEnum` para enums serializados.

## Decisão

Método sólido em 3 serviços (guardrails, evals, inference). Padrão "adapter + fake" consolidado. Correções menores acumuladas (conftest silencia httpx; StrEnum) — aplicar ao template quando conveniente, não bloqueiam. Próximo: `spec-svc-router` (rodada 4, ordem ARCHITECTURE §4) — primeiro consumidor real de svc-inference + svc-guardrails.

---

# RETRO — Rodada 4 (svc-router)

Quarto serviço; template com as 4 correções menores da rodada 3 aplicadas (§8.5: adapter+fake, conftest silencia httpx, StrEnum). Primeiro serviço que **combina duas dependências** (SBERT local + adapter LLM) e o de **maior superfície** (BM25, RRF, embedder, guards, 3 camadas, LLM). Veredito: F0→F7 até **G1–G8 todos PASS**.

## Resultados

| Gate | Resultado |
|------|-----------|
| G1 testes | 55 pass |
| G2 acurácia (SBERT) | 0.967 (29/30) |
| G3 fusão RRF | 5/5 (à mão) |
| G4 guards + armadilha | 6/6 |
| G5 lint+mypy | limpo |
| G6 contrato | OpenAPI válido |
| G7 security | fail-closed + SSRF |
| G8 perf overhead | P95 0.17ms |

## O que os padrões do template evitaram / entregaram

- **Adapter+fake em dobro** (embedder e LLM): gates rápidos usam Fake*, G2 usa SBERT real. O padrão §8.5 escalou para dois eixos sem atrito.
- **conftest silencia httpx** já no template → saída limpa desde o começo.
- **Guards com armadilha** pegou o caso "custo do produto" (não-finanças) e "ignore os pedidos" (não-guard) — exatamente o valor da §12.7.

## Fricção real (rodada 4) — a mais séria até agora

- **Background job roda em cwd default, não no cwd do serviço.** O comando de F0 (`touch models/.gitkeep && ... venv`) rodou fora do `svc-router`; o `&&` abortou no primeiro `touch` (dir `models/` inexistente) e o venv **nunca foi criado** — mas o job reportou "exit 0" porque a última instrução era um `echo`. Diagnóstico só apareceu ao tentar usar `.venv`. Custou uma rodada de depuração.
  - **Correções a levar ao template/processo:** (1) F0 deve criar TODOS os diretórios (`models/`, `evals/results/`) no scaffold, antes de qualquer `touch`; (2) comandos de background devem usar **paths absolutos** e não depender de cwd; (3) terminar scripts de setup com o **código de saída real** (`exit $rc`), não um `echo`, para o status refletir a verdade. Candidato forte a uma seção "F0 robusto" no template.

## Correção de escopo honesta

- **svc-router não implementa spans OTel próprios** (DECISIONS D6): observabilidade via `/metrics` (by_layer) + logs; a instrumentação GenAI vive no svc-inference (que a camada LLM chama). Spans HTTP próprios → BACKLOG. Nenhum gate afetado.

## Decisão

4/7 DONE. Método robusto mesmo no serviço de maior superfície. **1 correção de processo importante** (F0 robusto: dirs no scaffold + paths absolutos + exit real) a aplicar ao template antes da rodada 5. Próximo: `spec-svc-rag` (rodada 5, ordem ARCHITECTURE §4).

---

# RETRO — Rodada 5 (svc-rag)

Quinto serviço; template com F0 robusto aplicado (§11). Veredito: F0→F7 até **G1–G8 todos PASS**. O F0 robusto **eliminou a fricção de cwd/venv da rodada 4** — scaffold criou todos os dirs de uma vez, venv com path absoluto e `exit $rc` real; zero retrabalho de setup.

## Resultados

| Gate | Resultado |
|------|-----------|
| G1 testes | 55 pass |
| G2 Recall@3 (SBERT) | **1.000** (12/12) — iguala o baseline do AIO |
| G3 chunking + armadilha | 7/7 |
| G4 store + idempotência | 5/5 |
| G5 lint+mypy | limpo |
| G6 contrato | OpenAPI válido |
| G7 security | fail-closed + SSRF |
| G8 busca | P95 1.05ms |

## O que funcionou

- **F0 robusto pagou na hora**: a fricção nº1 da rodada 4 (background em cwd errado, venv fantasma) não repetiu. Correção de processo validada.
- **Adapter+fake em dois eixos de novo** (embedder Fake/SBERT + store InMemory/Qdrant): gates offline, produção plugável. Qdrant via httpx REST evitou dependência pesada.
- **Recall@3 1.000** com corpus sintético + distrator (armadilha): o golden com documento-distrator (§12.7) confirmou que o distrator não entra no topo.

## Fricção nova (rodada 5) — pequena

- **DNS em teste de SSRF**: `test_ssrf_public_ok` usava `example.com` (como no svc-router, onde passou), mas neste ambiente o DNS de `example.com` não resolveu → `ValueError`. Trocado por **IP público literal** (`8.8.8.8`), que não exige DNS. **Candidato ao template**: testes de allow-SSRF usam IP literal público, não hostname (evita dependência de DNS no ambiente de gate).

## Correção de escopo honesta

- **svc-rag não implementa spans OTel próprios** (DECISIONS D7): embeddings locais não são "GenAI generation"; observabilidade via /metrics+logs. Spans HTTP → BACKLOG. Nenhum gate afetado. (Mesma decisão do svc-router.)

## Decisão

5/7 DONE. Método estável e previsível — 3 rodadas seguidas (evals, inference, router, rag) sem fricção de lógica; só ajustes de ambiente/processo, cada um virando regra no template. **1 correção menor** (IP literal em teste SSRF) a aplicar quando conveniente. Próximo: `spec-svc-observability` (rodada 6, ordem ARCHITECTURE §4) — consolida a telemetria já emitida pelos anteriores.
