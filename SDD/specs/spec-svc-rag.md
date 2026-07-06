# SPEC — svc-rag v1.0

> Quinta spec do programa SDD (rodada 5). Derivada de `../SPEC_TEMPLATE.md` calibrado por RETRO rodadas 1–4 (inclui F0 robusto). Contrato único entre arquiteto e loop de agentes.

---

## 0. Metadados

| Campo | Valor |
|-------|-------|
| Serviço | `svc-rag` |
| Versão da spec | 1.0.0 |
| Status | **frozen** |
| Baseline de referência | AI-Orchestrator `fe3adc1` — `gateway/document_search.py`, `scripts/ingest_documents.py` (Qdrant, SBERT, chunking por seção), `gateway/community_summaries.py` (GraphRAG/Louvain) |
| Repo alvo | `~/Documentos/projeto-portifolio/microservicos-ai-orchestrator/svc-rag` |
| Data de congelamento | 2026-07-06 |

## 1. Contexto e problema

RAG sobre documentos não estruturados foi o que deu ao AI-Orchestrator respostas fundamentadas em políticas internas: `scripts/ingest_documents.py` faz **chunking por seção + SBERT + Qdrant**, e `document_search.py` expõe `search_documents` como tool aos agentes — medido **Recall@3 = 12/12 = 100%**. Há também a camada GraphRAG (`community_summaries.py`): comunidades Louvain offline + resumos pré-gerados (modularity 0.618), servidos como artefato sem tocar Neo4j no caminho da request.

Este serviço extrai a recuperação para uma **API independente**: ingestão (chunk + embed + store), busca semântica (`/v1/search`) e resumos de comunidade pré-gerados (GraphRAG opt-in). Consumidores previstos: `svc-orchestrator` (tool de busca aos agentes), qualquer app que precise de recuperação fundamentada.

Padrão herdado (template §8.5): o **vector store é um adapter atrás de interface** — `InMemoryStore` (numpy, cosseno) para dev/gates e `QdrantStore` para produção. O **embedder** é SBERT local (boot) com `FakeEmbedder` determinístico nos gates rápidos; o gate de **Recall** usa SBERT real (lento). GraphRAG serve um **artefato pré-gerado** (fora do caminho quente), com fixture determinística nos gates.

Lição institucionalizada: o golden de recuperação carrega **armadilhas** (documento distrator que compartilha palavras mas não responde) e **não é ajustável** para passar gate (§12.7).

## 2. Objetivo (uma frase)

Expor recuperação fundamentada como API stateless-de-lógica: ingestão com chunking por seção + embeddings, busca semântica com Recall@3 ≥ 0.80 sobre corpus configurável, e resumos de comunidade pré-gerados (GraphRAG opt-in), com vector store plugável (InMemory/Qdrant) e testável 100% offline.

## 3. Não-objetivos (o agente NÃO constrói)

- Geração de resposta (LLM) — svc-rag **recupera**; a síntese é do orchestrator/agentes.
- Servir LLM ou embeddings como serviço à parte — embedder é interno (SBERT).
- Roteamento de intenção — isso é `svc-router`.
- Cálculo de comunidades Louvain em runtime / escrita no Neo4j — GraphRAG serve **artefato pré-gerado** (build offline, fora do escopo do serviço).
- Sanitização / injection — isso é `svc-guardrails`.
- UI / crawler / conectores de fonte (Drive, S3) — ingestão recebe documentos já em texto.
- Re-ranking por LLM (nível 2) — fica no BACKLOG.

## 4. Glossário

| Termo | Definição neste contexto |
|-------|--------------------------|
| Documento | `{id, text, metadata}` recebido na ingestão |
| Chunk | Trecho de um documento após chunking (por seção + limite de tamanho) |
| Coleção | Namespace lógico de chunks (isola corpora distintos) |
| Vector store | Backend de vetores: `InMemoryStore` (gates) \| `QdrantStore` (prod) |
| Recall@k | Fração de queries cujo chunk relevante aparece no top-k |
| Comunidade | Cluster pré-computado (Louvain offline) com um resumo pré-gerado |
| GraphRAG | Recuperação por resumo de comunidade (artefato, opt-in) |
| Ingestão idempotente | Reingerir mesmo `id`+hash de conteúdo não duplica chunks |
| Armadilha | Documento distrator (compartilha termos, não responde) — anti-falso-positivo |

## 5. Contrato de API

> Fonte da verdade: `api/openapi.yaml` (OpenAPI 3.1), gerado na F1, validado com `openapi-spec-validator`. Rotas `/v1/`.

### 5.1 Endpoints

| Método | Rota | Auth | Descrição | Erros |
|--------|------|------|-----------|-------|
| POST | `/v1/ingest` | interna | Chunk + embed + store dos documentos (idempotente por id+hash) | 401, 422, 503 (store fora) |
| POST | `/v1/search` | interna | Busca semântica; retorna chunks ranqueados com score | 401, 422, 503 (store/embedder fora) |
| GET | `/v1/collections` | interna | Lista coleções + contagem de chunks | 401 |
| GET | `/v1/community/{id}` | interna | Resumo de comunidade pré-gerado (GraphRAG opt-in) | 401, 404, 503 (GraphRAG off) |
| GET | `/health` | nenhuma | Liveness + readiness (deps: embedder, vector_store, graphrag) | — |
| GET | `/metrics` | interna | Contadores (ingest, search) + latências; `source: live` | 401 |

### 5.2 Schemas principais (Pydantic v2 espelha o OpenAPI)

```yaml
Document: {id: str, text: str, metadata: object}
IngestRequest: {collection: str = "default", documents: list[Document]}
IngestResponse: {collection, n_documents, n_chunks, n_skipped_idempotent}

SearchRequest: {query: str, collection: str = "default", top_k: int = 3}
Hit: {chunk_id: str, doc_id: str, text: str, score: float, metadata: object}
SearchResponse: {query: str, hits: list[Hit], collection: str}

CommunitySummary: {id: str, title: str, summary: str, members: list[str]}

Erro de negócio: 422 {error, detail, rule}
Erro interno: 500 genérico — stack só em log.
```

### 5.3 Contrato de erro
- Negócio: `422 {error, detail, rule}`. Store/embedder fora: `503`. GraphRAG off e comunidade pedida: `503`.
- Interno: `500` genérico; stack só em log.

## 6. Modelo de dados e estado

- **Estado = os vetores no vector store** (adapter). `InMemoryStore`: dict por coleção com chunks + embeddings (numpy); reinício perde dados (aceitável em dev/gates). `QdrantStore`: coleção Qdrant por `collection`; auth por API key (config do operador).
- **Chunking** (`src/rag_svc/chunking.py`): split por seções (headers Markdown `#`/`##`) e, dentro de cada seção, por limite de caracteres com overlap configurável; nunca corta no meio de palavra; preserva a ordem e a origem (`doc_id`, offset).
- **Idempotência**: `chunk_id = sha256(doc_id + chunk_index + content)[:16]`; reingestão do mesmo conteúdo é no-op (conta em `n_skipped_idempotent`).
- **GraphRAG**: artefato `models/communities.json` (pré-gerado offline — fora do escopo do serviço gerar), carregado no boot se presente; ausente → GraphRAG off, `/v1/community/*` responde 503, `/health` marca `graphrag: absent`. Isolamento de artefatos (template §6): comunidades são dados de leitura, não colidem com evals/results.

## 7. Configuração (env — 12-factor)

| Variável | Default | Obrigatória | Efeito |
|----------|---------|-------------|--------|
| `INTERNAL_KEY` | — | sim (prod) | Auth interna; ausente → 401 (fail-closed) |
| `ALLOW_OPEN_ACCESS` | `0` | não | `1` libera sem key (dev; warning no boot) |
| `EMBED_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | não | SBERT local (mesmo do ecossistema) |
| `VECTOR_STORE` | `qdrant` | não | `qdrant` \| `memory` (memory p/ dev/gates) |
| `QDRANT_URL` | `http://localhost:6333` | não | Endpoint do Qdrant |
| `QDRANT_API_KEY` | — | não | API key do Qdrant (fail-closed no banco) |
| `CHUNK_MAX_CHARS` | `800` | não | Tamanho-alvo do chunk |
| `CHUNK_OVERLAP` | `100` | não | Overlap entre chunks da mesma seção |
| `GRAPHRAG_ENABLED` | `0` | não | `1` liga `/v1/community/*` (exige artefato) |
| `MAX_DOC_CHARS` | `100000` | não | 422 por documento acima disso |
| `RATE_LIMIT_PER_MIN` | `120` | não | Sliding window por IP |
| `OTEL_ENABLED` | `0` | não | OTLP → Collector; fora = no-op |
| `LOG_LEVEL` | `INFO` | não | Log JSON estruturado |

> Fail-closed na segurança; degradação graceful na telemetria, no store e no embedder.

## 8. NFRs

### 8.1 Segurança
- Transversais (ARCHITECTURE §3.1): `hmac.compare_digest`, fail-closed, Swagger off, `.dockerignore`, `.env` fora do git.
- `QDRANT_URL` é config de operador; validar esquema http/https + bloquear metadata/loopback (anti-SSRF) no boot salvo `ALLOW_LOCAL_STORE=1`.
- Texto de documento/query é dado não confiável: nunca em log sem escape, nunca ecoado em erro.

### 8.2 Performance
- `/v1/search` (InMemoryStore, embedder quente): **P95 < 80 ms** em CPU (embedding domina).
- Latência com Qdrant real: medida e reportada, não gateada.

### 8.3 Observabilidade
- Log JSON por operação: `{trace_id, op, collection, n_hits|n_chunks, latency_ms}` — sem texto completo.
- `/metrics`: `ingests_total`, `searches_total`, `chunks_total`, `latency_p50/p95`; `source: live`.
- Embeddings via SBERT local não são "GenAI generation" (sem tokens de geração) — sem spans `gen_ai.*`; spans HTTP se `OTEL_ENABLED=1` (BACKLOG se não trivial).

### 8.4 Resiliência
- Embedder fora no boot → ingest/search retornam 503 claro; `/health` degraded. Serviço sobe.
- Vector store (Qdrant) fora → 503 nas operações que o exigem; nunca crash.
- GraphRAG sem artefato → `/v1/community/*` 503; resto do serviço normal.
- Deadline por request.

## 9. Dependências

| Dependência | Tipo | Runtime obrigatória? | Se ausente |
|-------------|------|----------------------|------------|
| sentence-transformers (local) | lib | sim p/ ingest/search | 503 nas ops; /health degraded |
| Qdrant | serviço | não (`VECTOR_STORE=memory` p/ dev/gates) | 503 se `VECTOR_STORE=qdrant` e fora |
| artefato de comunidades | arquivo | não (só GraphRAG) | /v1/community 503 |
| OTel Collector | infra | não | no-op |

> Gates: Recall (G2) usa SBERT real + `InMemoryStore` (gate **lento**, sem Qdrant); chunking/store/API usam FakeEmbedder + InMemory (rápidos, offline). Nenhum gate exige Qdrant/Neo4j no ar.

## 10. Gates de aceitação

> Velocidade: G2 é **lento** (SBERT real); os demais **rápidos**. `make gates` roda todos.

| # | Gate | Velocidade | Comando | Threshold | Baseline AIO |
|---|------|-----------|---------|-----------|--------------|
| G1 | Testes | rápido | `python -m pytest -q` | 100% pass, ≥ 50 testes | — |
| G2 | Recall@3 (SBERT real + InMemory) | lento | `python evals/eval_recall.py` | **≥ 0.80** no golden | Recall@3 100% (12/12) |
| G3 | Chunking (determinístico) | rápido | `python evals/eval_chunking.py` | seções corretas; sem perda de conteúdo; sem corte no meio de palavra; **armadilha** | chunking por seção do AIO |
| G4 | Vector store + idempotência | rápido | `python evals/eval_store.py` | ranking cosseno correto; reingestão não duplica | — |
| G5 | Lint + tipos | rápido | `ruff check . && python -m mypy src/` | 0 erros | — |
| G6 | Contrato | rápido | `openapi-spec-validator api/openapi.yaml && python -m pytest tests/test_contract.py` | 0 violações; toda rota testada | — |
| G7 | Security | rápido | `python -m pytest tests/test_security.py` | fail-closed, 401, SSRF do QDRANT_URL, stack não vaza | auditoria 0 |
| G8 | Perf (InMemory) | rápido¹ | `python evals/bench_latency.py` | P95 < 80 ms (FakeEmbedder) | — |

¹ Bench usa FakeEmbedder para medir só overhead de busca (embedding+cosseno), não o custo do SBERT.

**Dogfood (o agente constrói em F2–F4):**
- *FakeEmbedder determinístico* (hash → vetor) para gates rápidos.
- *golden de recuperação* (≥ 10 queries; corpus de políticas estilo AIO) usado no G2 com SBERT real. **Armadilha obrigatória**: documento distrator que compartilha palavras da query mas não a responde — não deve entrar no top-k acima do relevante.
- *eval_chunking*: doc com seções + parágrafo longo → chunks por seção, tamanho respeitado, conteúdo reconstruível; armadilha = linha parecendo header dentro de bloco de código não vira seção.
- *eval_store*: ranking cosseno com vetores conhecidos; reingestão do mesmo id+conteúdo não duplica.

## 11. Plano de fases

| Fase | Entregável | Verificação | Stop condition |
|------|-----------|-------------|----------------|
| F0 | Scaffold robusto (template §11): repo no destino, **todos os dirs de uma vez**, pyproject, Dockerfile (SBERT no build), Makefile (`python -m`), CI, SPEC.md | `docker build .` + `make check` + `.venv/bin/python` existe | build verde |
| F1 | `api/openapi.yaml` + schemas Pydantic (Ingest/Search/Community) | G6 | contrato validado |
| F2 | Chunking + embedder (Fake+SBERT) + InMemoryStore + testes | G1 subset + G3 + G4 + G5 | chunking+store corretos |
| F3 | Ingestão + busca (search_documents) + golden + `eval_recall.py` | G2 (SBERT) | Recall@3 ≥ 0.80 |
| F4 | GraphRAG (carga de artefato + `/v1/community`) + QdrantStore adapter | G1 subset | comunidade servida (fixture) |
| F5 | API completa + auth + SSRF + rate-limit + deadline | G6 + G7 | security PASS |
| F6 | `/health` + `/metrics` + OTel opt-in + logs | smoke via compose | telemetria ok |
| F7 | Bench + README (gates medidos) + DECISIONS.md | **G1–G8 todos na mesma execução** | **DONE** |

## 12. Regras para o agente

1. Escopo = esta spec. Fora → `BACKLOG.md`.
2. Contradição/gate impossível → PARAR e perguntar.
3. Mesmo gate falhando após 3 correções distintas → parar, diagnóstico em `DECISIONS.md`.
4. Commits convencionais, ≥ 1 por fase. Nunca commitar `.env`, modelos, artefatos, `evals/results/*`.
5. Só reportar números medidos pelos comandos da §10.
6. Dependência nova fora do pyproject inicial (fastapi, uvicorn, pydantic, httpx, sentence-transformers, numpy, pytest, ruff, mypy, openapi-spec-validator, pyyaml) → justificar em `DECISIONS.md`. **Não** adicionar cliente Qdrant pesado se `httpx` resolver a API REST.
7. **Golden com armadilha obrigatória** (§12.7): distrator na recuperação; header-falso no chunking.
8. Vector store e embedder via adapter + fake; nenhum gate exige Qdrant/Neo4j no ar. G2 usa SBERT real (lento).
9. **Não tocar:** nada fora deste repo. Não gerar comunidades Louvain em runtime (artefato é pré-gerado).

## 13. Riscos

| Risco | Prob. | Impacto | Mitigação |
|-------|-------|---------|-----------|
| Recall G2 < 0.80 com golden pequeno | M | M | Corpus com chunks bem separados; se falhar, reforçar exemplares antes de mexer no método |
| Chunking perde/duplica conteúdo | M | A | G3 reconstrói o texto dos chunks e compara; overlap contado; sem corte no meio de palavra |
| Idempotência quebrada (duplica ao reingerir) | M | M | `chunk_id` por hash de conteúdo; G4 reingerindo o mesmo doc |
| SSRF via QDRANT_URL | B | A | Validação de esquema + bloqueio metadata/loopback no boot; G7 |
| Cliente Qdrant acopla e complica gates | B | M | QdrantStore via httpx REST atrás de interface; gates usam InMemory |

## 14. Definição de DONE

- [ ] G1–G8 PASS na mesma execução; log em `evals/results/`
- [ ] `docker compose up` + smoke (`/v1/ingest` + `/v1/search` retorna o chunk relevante no topo)
- [ ] README: como rodar/testar, tabela de gates com números medidos, exemplo ingest+search
- [ ] `DECISIONS.md` com desvios; `BACKLOG.md` com fora-de-escopo (re-rank LLM, conectores de fonte)
- [ ] Zero secrets/artefatos no git
- [ ] Entrada em `../RETRO.md` (rodada 5): F0 robusto resolveu a fricção de cwd? novas fricções?
