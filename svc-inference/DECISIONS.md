# DECISIONS — svc-inference

Desvios da SPEC e decisões técnicas com justificativa.

## D1 — Fachada OpenAI-compatível, backend atrás de interface
O contrato exposto é o subset OpenAI (`chat.completion`, chunks `chat.completion.chunk`, `usage`). O vendor (Ollama) fica atrás de um `Backend` Protocol. Consumidores (svc-router, svc-orchestrator, svc-evals como judge) não acoplam a Ollama; trocar por vLLM/TGI é um novo adapter sem quebrar o contrato.

## D2 — FakeBackend determinístico para gates 100% offline
Regra da spec (§12.8): nenhum gate pode exigir Ollama no ar. `FakeBackend` devolve conteúdo e usage previsíveis (`completion_tokens = len(reply.split())`) e é configurável para falhar (transporte vs. 4xx). Ollama real só no `make smoke` opcional. Todos os G1–G8 rodam sem rede.

## D3 — Usage sempre na fonte, nunca estimado
A fachada lê `prompt_tokens`/`completion_tokens` do que o backend reporta (Ollama: `prompt_eval_count`/`eval_count`). Se o backend não reportar, reflete o que veio (0 explícito). Reproduz a lição do AIO (causa-raiz do `tokens=0` era instrumentação fora do trace). G3 prova a propagação até `/metrics`.

## D4 — 4xx do backend NÃO abre o circuito (armadilha do dogfood)
Circuit breaker só conta **falha de transporte** (`BackendError`); um 4xx do backend é `BackendBusiness` e retorna 503 sem incrementar o contador do circuito. Erro de negócio não é indisponibilidade. G4 tem o caso-armadilha explícito (5 chamadas 4xx → circuito segue CLOSED).

## D5 — CircuitState com StrEnum (py3.12)
`CircuitState(StrEnum)` em vez de `(str, Enum)` — idioma correto do 3.12, resolve UP042 do ruff e mantém `.value` string para o JSON de `/health` e `/metrics`.

## Desvios da SPEC
Nenhum desvio funcional. Gates G1–G8 conforme §10. Tuning de hardware do AIO citado como referência documentada, não re-medido (§12.5).
