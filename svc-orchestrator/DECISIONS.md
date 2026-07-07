# DECISIONS — svc-orchestrator

Desvios da SPEC v1.0.0 (congelada em 2026-07-06) e decisoes tecnicas, registrados na
reconciliacao as-built (SPEC §15). Nenhum afeta gate; todos os G1–G8 PASS.

## D1 — HITL antes do fan-out (ordem da §5.3 ajustada)

A §5.3 numerava HITL como passo 4 (depois do fan-out), mas o glossario (§4) define HITL
como "pausa **antes de despachar** uma operacao de escrita". Implementado coerente com o
glossario: `sanitize → route → HITL → fan-out → fan-in`. Pausar antes do fan-out e mais
barato (nao gasta rag/inference numa operacao que pode ser rejeitada) e mais seguro.
G3 (12/12) valida pause/resume e a armadilha.

## D2 — Env extra: `CIRCUIT_RESET_S` (default 30)

O threshold do circuito era configuravel (§7) mas o tempo de reset nao. Adicionado
`CIRCUIT_RESET_S` para testar HALF-OPEN de forma deterministica sem sleep longo.

## D3 — Falha parcial no fan-out degrada, nao derruba (refinamento da §8.4)

- guardrails/router fora (antes do fan-out) → **503** (nao-stream) / evento `error` (SSE),
  como especificado. Guardrails permanece fail-closed.
- inference fora em **um agente** do fan-out → evento `error` + resposta placeholder
  `[dominio: indisponivel]`; o fluxo segue com os demais dominios (degradacao explicita,
  §8.4 "fan-out parcial").
- inference fora na **sintese** (fan-in multi-dominio) → entrega o combinado bruto das
  respostas dos agentes (degradacao, nao 503).
- 4xx de downstream (`DownstreamBusiness`) → 503 sem abrir circuito (so transporte conta).

## D4 — Deadline global (`REQUEST_DEADLINE_S` → 504) nao implementado no v1

Declarado na §7/§8.4 e no contrato (504), mas o v1 nao aplica deadline global por request:
na pratica o teto e dado pelos timeouts por downstream (`DOWNSTREAM_TIMEOUT_S`, um por
chamada). Implementar 504 exigiria orquestracao assincrona/cancelamento — fora do custo
do v1. O 504 permanece no contrato como reservado; implementacao → BACKLOG.

## D5 — `OTEL_ENABLED` e no-op (sem exporter OTLP)

Mesma decisao D7 do svc-rag/svc-router: observabilidade via `/metrics` + logs JSON +
**traceparent W3C propagado a todos os downstream** (§8.3, testado no G7). Spans OTel
HTTP proprios → BACKLOG.

## D6 — Sem CI no repo (F0)

Nenhum servico do ecossistema tem workflow de CI; os gates rodam via `make gates`.
Consistencia mantida; CI de ecossistema → BACKLOG do template.

## D7 — SSE termina com evento terminal `done: [DONE]`

Nao especificado na §5.2, mas espelha o padrao do svc-inference/baseline: o cliente tem
um marcador inequivoco de fim de stream, inclusive apos `error`. G4 valida.

## D8 — Contrato 422: shape de validacao FastAPI, nao `{error, detail, rule}`

A §5.4 previa `422 {error, detail, rule}` (BusinessError), mas todos os 422 reais do
servico sao erros de validacao Pydantic/FastAPI (`{detail: [...]}`) — nao ha regra de
negocio propria que gere 422 (bloqueio e 403, pausa e `paused`). O contrato foi
reconciliado: `ValidationError {detail: array}` no openapi; `BusinessError` removido.

## D9 — Historico de commits: 1 commit inicial consolidado

A regra §12.4 pede ≥1 commit por fase; o trabalho F0–F7 ocorreu em sessao continua e o
repo foi commitado consolidado (mesma convencao do svc-rag `095d40c`). As fases estao
rastreaveis pela SPEC §11 e pelos artefatos por fase.
