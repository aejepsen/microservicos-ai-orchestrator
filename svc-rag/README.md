# svc-rag

Recuperação fundamentada como API stateless: **ingestão** (chunking por seção + embeddings SBERT), **busca semântica** (`search_documents`) e **resumos de comunidade** pré-gerados (GraphRAG opt-in). Vector store plugável (InMemory/Qdrant). Extraído de `document_search.py` + `ingest_documents.py` + `community_summaries.py` do AI-Orchestrator.

Quinto serviço do programa SDD (`../SDD/`). Contrato: `api/openapi.yaml`.

## Gates (medidos)

| Gate | Métrica | Resultado | Threshold | Baseline AIO |
|------|---------|-----------|-----------|--------------|
| G1 | Testes | **55 pass** | 100%, ≥50 | — |
| G2 | Recall@3 (SBERT) | **1.000** (12/12) | ≥0.80 | 100% (12/12) |
| G3 | Chunking + armadilha | **7/7** (header-em-código ignorado) | 0 divergência | chunking por seção |
| G4 | Store + idempotência | **5/5** | ver dogfood | — |
| G5 | Lint+tipos | **ruff+mypy limpos** | 0 erros | — |
| G6 | Contrato | **OpenAPI válido** | 0 violações | — |
| G7 | Security | **fail-closed + SSRF OK** | ver tests | auditoria 0 |
| G8 | Perf (busca) | **P95 1.05 ms** | <80 ms (FakeEmbedder) | — |

## Como rodar

```bash
make venv          # cria .venv + deps (inclui SBERT via torch)
make gates         # G1–G8 (G2 carrega SBERT; demais offline)
VECTOR_STORE=memory INTERNAL_KEY=k make run   # sobe API em :8204

INTERNAL_KEY=k docker compose up --build   # com Qdrant real (VECTOR_STORE=qdrant)
```

## Uso

```bash
# ingerir documentos (chunk + embed + store)
curl -s localhost:8204/v1/ingest -H 'X-Internal-Key: k' \
  -H 'content-type: application/json' -d '{
    "collection":"politicas",
    "documents":[{"id":"reembolso","text":"# Reembolso\n\nDespesas reembolsadas em 30 dias."}]}'

# buscar
curl -s localhost:8204/v1/search -H 'X-Internal-Key: k' \
  -H 'content-type: application/json' \
  -d '{"query":"em quantos dias reembolsa?","collection":"politicas","top_k":3}'
# -> {"hits":[{"doc_id":"reembolso","text":"...","score":0.82}]}
```

## Contrato

- `POST /v1/ingest` — chunk + embed + store (idempotente por id+hash) → contagens
- `POST /v1/search` — busca semântica → chunks ranqueados (`chunk_id`, `doc_id`, `text`, `score`)
- `GET /v1/collections` — coleções + nº de chunks
- `GET /v1/community/{id}` — resumo de comunidade pré-gerado (GraphRAG opt-in)
- `GET /health` (deps: embedder, vector_store, graphrag) · `GET /metrics` (`source: live`)

## Notas

- **Vector store**: `VECTOR_STORE=qdrant` (prod, via httpx REST) ou `memory` (dev/gates). Gates usam InMemory + FakeEmbedder → 100% offline.
- **Chunking por seção** (headers Markdown), sem cortar palavra, ignora header dentro de bloco de código.
- **GraphRAG** serve artefato `models/communities.json` pré-gerado (Louvain offline é build externo); off por default.
- **Idempotência** por hash de conteúdo; reingerir não duplica.
- Auth fail-closed, anti-SSRF no `QDRANT_URL`, Swagger off. Decisões: `DECISIONS.md`.
