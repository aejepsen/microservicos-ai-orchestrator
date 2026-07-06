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
