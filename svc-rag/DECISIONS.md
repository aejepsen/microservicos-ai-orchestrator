# DECISIONS — svc-rag

Desvios da SPEC e decisões técnicas com justificativa.

## D1 — Vector store como adapter (InMemory + Qdrant via httpx REST)
`VectorStore` é interface; `InMemoryStore` (numpy cosseno) serve dev/gates, `QdrantStore` serve produção. Qdrant é falado via **httpx REST** (não o cliente `qdrant-client` pesado) — mantém o pyproject enxuto e os gates offline. Mesmo padrão adapter+fake do ecossistema (template §8.5).

## D2 — Recall (G2) usa SBERT real + InMemory; demais usam FakeEmbedder
Recuperação semântica só é significativa com embeddings reais → G2 carrega SBERT (gate lento). Chunking, store, API e perf usam `FakeEmbedder` (hash de palavras, captura sobreposição léxica) → rápidos e offline. Threshold Recall@3 = 0.80, abaixo do 100% do AIO (que tinha corpus de políticas real).

## D3 — Idempotência por hash de conteúdo
`chunk_id = sha256(doc_id|index|conteúdo)[:16]`. Reingerir o mesmo documento é no-op (contado em `n_skipped_idempotent`). G4 comprova reingestão sem duplicar.

## D4 — Chunking por seção ignora headers dentro de code fence
`_split_sections` rastreia blocos de código (```) e não trata linha `# ...` interna como seção. Split por tamanho nunca corta palavra; overlap por palavras. Armadilha do G3 (header falso em código) cobre isso — cumpre §12.7.

## D5 — GraphRAG serve artefato pré-gerado, não o gera
`community.py` só carrega `models/communities.json` (Louvain offline é responsabilidade de um build externo — §3 não-objetivo). Sem artefato ou `GRAPHRAG_ENABLED=0` → `/v1/community/*` responde 503; resto do serviço normal.

## D6 — Anti-SSRF no QDRANT_URL
`QDRANT_URL` (config de operador) é validado no boot: só http/https, bloqueio de metadata/loopback salvo `ALLOW_LOCAL_STORE=1`. URL inválida cai para InMemory com log de erro (degradação, não crash). G7 cobre.

## D7 — OTel spans deferidos (config presente, no-op) → BACKLOG
Embeddings SBERT local não são "GenAI generation" (sem tokens de geração), então spans `gen_ai.*` não se aplicam. Observabilidade via `/metrics` + logs JSON. Spans HTTP próprios → BACKLOG; nenhum gate depende deles.

## D8 — QdrantStore: point id UUID determinístico (bug E2E)
Qdrant só aceita ids uint64/UUID; o `chunk_id` (sha256[:16] hex) era rejeitado com 400 e o upsert ignorava a resposta — pontos nunca eram gravados (search 200 com 0 hits). Fix: id = `uuid5(NAMESPACE_URL, chunk_id)` (determinístico ⇒ idempotência preservada), `chunk_id` original vai no payload e é devolvido nos hits; upsert usa `?wait=true` e `raise_for_status()` em upsert/search (fail-closed). Descoberto na FASE 8 (E2E) — InMemory/fakes não exercitavam a validação de id do Qdrant real.

## Desvios da SPEC
Sem desvio funcional dos gates. D7 é a única redução de escopo (OTel spans → BACKLOG), justificada: observabilidade coberta por /metrics+logs.
