# BACKLOG — svc-orchestrator

Fora do escopo da SPEC v1.0.0.

- Historico de conversa de longo prazo (banco)
- Spans OTel HTTP proprios
- LangGraph (se o grafo crescer muito)
- Confirmacao no nivel da tool call (interceptar POST/PUT/DELETE)
- Deadline global por request (REQUEST_DEADLINE_S -> 504) — v1 usa timeouts por downstream (DECISIONS D4)
- Exporter OTLP real quando OTEL_ENABLED=1 (DECISIONS D5)
