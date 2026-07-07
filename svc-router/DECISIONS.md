# DECISIONS — svc-router

Desvios da SPEC e decisões técnicas com justificativa.

## D1 — Fusão híbrida por RRF a nível de rota
Denso (max cosseno da query vs. exemplares da rota) e léxico (max BM25) são convertidos em ranks base-1 e fundidos por Reciprocal Rank Fusion (`1/(k+rank)`). O vencedor sai do ranking fundido; o **threshold de decisão usa o cosseno denso** do vencedor (interpretável, mesma semântica do AIO), não o score RRF (que é pequeno por construção). Ranks começam em 1 (G3 valida à mão).

## D2 — Camada LLM como adapter + FakeLLM (padrão consolidado)
A camada 3 (fallback LLM) fala HTTP OpenAI-compat com `svc-inference` (`HttpLLM`), off por default. Gates usam `FakeLLM` determinístico. Mesmo molde do judge (svc-evals) e do backend (svc-inference) — template §8.5. Nenhum gate exige svc-inference no ar.

## D3 — Gate de acurácia (G2) usa SBERT real (lento), demais usam FakeEmbedder
Roteamento semântico só é significativo com embeddings reais; G2 carrega o SBERT (gate lento, ao fim/background). Os demais gates (fusão, guards, perf, API) usam `FakeEmbedder` hash-determinístico → rápidos e offline. Threshold do G2 = 0.85, abaixo do 94.1% do AIO (que tinha golden auditado grande); golden aqui é sintético de 30 casos. Medido: **0.967** (29/30; o único miss — "pagar um boleto atrasado" → rh/vendas — é ruído de exemplar, não bug de método).

## D4 — Guards ancorados a contexto + armadilha obrigatória
Guards léxicos disparam só com contexto (ex.: `custo` mas não `custo do produto`; `quem aprova` mas não `ignore os pedidos`). O golden de guards (G4) inclui armadilhas — uso legítimo de palavra-gatilho que NÃO deve disparar. Cumpre §12.7 do template.

## D5 — Anti-SSRF no LLM_URL
Mesmo sendo config de operador (não do request), `LLM_URL` é validado no boot: só http/https, bloqueio de metadata/loopback salvo `ALLOW_LOCAL_LLM=1`. G7 cobre.

## D6 — OTel spans deferidos (config presente, no-op) → BACKLOG
`OTEL_ENABLED` existe e a observabilidade é servida por `/metrics` (by_layer) + logs JSON. Spans OTel GenAI não se aplicam (não há geração LLM aqui — a camada LLM é classificação via svc-inference, que já instrumenta). Spans HTTP próprios ficam no BACKLOG; nenhum gate depende deles.

## Desvios da SPEC
Sem desvio funcional dos gates. D6 é a única redução de escopo (OTel spans próprios → BACKLOG), justificada: observabilidade coberta por /metrics+logs, e a instrumentação GenAI vive no svc-inference.
