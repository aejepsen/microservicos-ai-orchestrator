# DECISIONS — svc-guardrails

Desvios da SPEC e decisões técnicas com justificativa.

## D1 — E501 relaxado em tests/ e evals/ (não em src/)
`ruff` line-length permanece 100 no código-fonte. Em `tests/*` e `evals/*`, E501 é ignorado via `per-file-ignores`: asserts com mensagens descritivas e linhas de `print` de relatório de gate ficam mais legíveis inteiras. Código-fonte não recebe exceção. Regex `_INSTR` em `patterns_pt.py` recebe `# noqa: E501` pontual — quebrar a alternância prejudica a leitura.

## D2 — Threshold OOD calibrado por Youden sobre LOO
A SPEC exige threshold via LOO (proíbe hardcode do 0.48 do AIO). Implementado: resíduo LOO de cada amostra in-domain vs. resíduo do conjunto OOD de calibração; threshold = ponto de Youden (max TPR−FPR). Corpus piloto (40 in / 30 out) deu AUC_LOO 0.9992, threshold ≈ 0.817 — número do próprio corpus, não herdado.

## D3 — AUC por Mann-Whitney (sem sklearn)
AUC calculada via estatística U de Mann-Whitney (ranks), evitando dependência de scikit-learn. Mantém o pyproject enxuto (numpy já presente).

## D4 — Detecção de injection sobre texto ORIGINAL
A sanitização neutraliza delimitadores de chat, mas a detecção roda sobre o texto pré-sanitização: um `<|im_start|>` recebido é evidência de ataque mesmo que a sanitização o remova. Sanitização protege o downstream; detecção preserva o sinal.

## D5 — venv não-relocável após mover a pasta
Mover o repo para `microservicos-ai-orchestrator/` quebrou os shebangs dos wrappers do `.venv` (`mypy`, `uvicorn`, `ruff`). Gates rodam via `.venv/bin/python -m <tool>` (Makefile já usa esse padrão) ou via Docker (runtime real). venv local recriado com `make venv` após o move. Não afeta produção (Dockerfile builda fresco).

## Desvios da SPEC
Nenhum desvio funcional. Todos os gates G1–G8 implementados conforme §10.
