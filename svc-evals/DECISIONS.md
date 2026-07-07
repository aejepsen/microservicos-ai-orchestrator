# DECISIONS — svc-evals

Desvios da SPEC e decisões técnicas com justificativa.

## D1 — Judge é adapter HTTP off por default
svc-evals é rodada 2, antes de `svc-inference` (rodada 3). Para não criar dependência fora de ordem, o scorer `llm_judge` fala HTTP com um endpoint OpenAI-compatível genérico (`HttpJudge`), ligado só com `JUDGE_ENABLED=1`. Determinismo: `temperature=0`, `response_format=json_object`, parse tolerante a lixo em volta do JSON. Dogfood usa `FakeJudge` determinístico — gates rodam sem rede.

## D2 — Métricas em stdlib (sem numpy/sklearn)
Accuracy, macro-F1 e recall@k implementados em Python puro. svc-evals não carrega modelo nem faz álgebra pesada; manter o pyproject enxuto (só fastapi/pydantic/httpx). Diferente do svc-guardrails, que precisa de numpy para o subespaço OOD.

## D3 — JSONPath próprio, subset seguro
O `output_pointer` do modo live usa um navegador de caminho próprio (`jsonpath.py`) que só resolve chaves de dict e índices de lista — nunca `eval`/`exec`. Golden e resposta são dados não confiáveis; nada é interpretado como código.

## D4 — Anti-SSRF no modo live e no judge
URLs de `target`/`judge` são validadas: só `http/https`, e resolução de host bloqueia redes privadas + metadata cloud (`169.254.0.0/16`) e loopback, salvo `ALLOW_LOCAL_TARGET=1`. Evita que um golden malicioso faça o serviço bater em endpoints internos.

## D5 — ResultsStore ignora artefatos não-payload (bug de dogfood corrigido)
Os eval scripts (`eval_engine/scorers/judge/bench`) escrevem seus próprios artefatos em `evals/results/`, mesma pasta que o `ResultsStore` lê. O primeiro `make gates` quebrou: `GET /v1/results` tentou ler `engine_*.json` como payload de rodada (`KeyError: 'suite'`). Correção em dois níveis: (a) `ResultsStore` só considera arquivos com todas as chaves de payload de rodada; (b) o bench usa `results_dir` temporário isolado. Robustez também vale em produção (pasta com arquivos estranhos não derruba o endpoint).

## Desvios da SPEC
Nenhum desvio funcional. Gates G1–G8 conforme §10 da spec.
