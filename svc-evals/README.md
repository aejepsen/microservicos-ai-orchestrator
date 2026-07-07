# svc-evals

Motor de avaliação por golden-set como API stateless: carrega casos JSONL, aplica **scorers** plugáveis, computa métricas com **gates** numéricos (PASS/FAIL) e persiste artefatos rotulados com **fonte** (`live`/`eval`/`estimate`). Extraído do padrão de evals do AI-Orchestrator (`evals/*`, `eval_results.py`).

Segundo serviço do programa SDD (`../SDD/`). Contrato: `api/openapi.yaml`. Não serve LLM — o juiz é adapter HTTP opcional (off por default).

## Gates (medidos)

| Gate | Métrica | Resultado | Threshold | Baseline AIO |
|------|---------|-----------|-----------|--------------|
| G1 | Testes | **54 pass** | 100%, ≥50 | — |
| G2 | Motor de gate | **10/10 casos** (bordas incl.) | 100% | — |
| G3 | Scorers | **10/10 checks** | 0 divergência | Recall@3, routing reproduzidos |
| G4 | Judge determinístico | **faithfulness 0.975** | ≥0.90, determinístico | 97.5% |
| G5 | Lint+tipos | **ruff+mypy limpos** | 0 erros | — |
| G6 | Contrato | **OpenAPI válido** | 0 violações | — |
| G7 | Security | **fail-closed + SSRF OK** | ver tests | auditoria 0 |
| G8 | Perf | **/results P95 1.6ms · runner 0.1ms** | <50 / <300 ms | — |

## Como rodar

```bash
make venv          # cria .venv + deps (leves, sem modelo local)
make gates         # G1–G8 na mesma execução
make run           # sobe API em :8201 (exige INTERNAL_KEY)

INTERNAL_KEY=troque docker compose up --build
```

## Uso

```bash
# roda suite registrada com gate
curl -s localhost:8201/v1/run -H 'X-Internal-Key: <key>' \
  -H 'content-type: application/json' -d '{"suite":"routing_accuracy"}'
# -> {"metric":"macro_f1","value":1.0,"passed":true,"source":"eval",...}

# roda golden inline com scorer + gate
curl -s localhost:8201/v1/run -H 'X-Internal-Key: <key>' \
  -H 'content-type: application/json' -d '{
    "golden_inline":[{"expected":"a","response":"a"}],
    "scorer":"exact_match",
    "gate":{"metric":"pass_rate","comparator":">=","threshold":0.9}}'
```

## Contrato

- `POST /v1/run` — roda suite (registrada ou inline); gateia; persiste artefato → `{metric, value, passed, source}`
- `GET /v1/suites` — suites registradas
- `GET /v1/results` — agregado das últimas rodadas (cache)
- `GET /v1/results/{suite}` — última rodada de uma suite
- `GET /health` · `GET /metrics`

## Scorers built-in

`exact_match` · `contains` · `regex_match` · `numeric_threshold` · `classification` (accuracy+macro-F1) · `recall_at_k` · `llm_judge` (adapter opcional).

## Notas

- **Stateless**, zero LLM local, zero banco. Gates 100% offline (judge mockado no dogfood).
- **Modo live**: chama endpoint do serviço-alvo por caso; guarda **anti-SSRF** (bloqueia metadata/loopback; só http/https).
- **Judge**: HTTP OpenAI-compatível, `JUDGE_ENABLED=0` por default (svc-evals não depende de svc-inference).
- Auth fail-closed, Swagger off, `.env`/`results` fora do git. Decisões: `DECISIONS.md`.
