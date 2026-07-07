"""Ingestão e busca: orquestra chunking + embedder + vector store."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rag_svc.chunking import chunk_document
from rag_svc.embedder import Embedder
from rag_svc.store import Hit, StoredChunk, VectorStore, chunk_id


@dataclass(frozen=True)
class IngestResult:
    n_documents: int
    n_chunks: int
    n_skipped_idempotent: int


def ingest_documents(
    documents: list[dict[str, Any]],
    collection: str,
    embedder: Embedder,
    store: VectorStore,
    *,
    max_chars: int,
    overlap: int,
) -> IngestResult:
    all_chunks: list[StoredChunk] = []
    texts: list[str] = []
    for doc in documents:
        doc_id = str(doc["id"])
        metadata = doc.get("metadata", {}) or {}
        for ch in chunk_document(doc["text"], max_chars, overlap):
            cid = chunk_id(doc_id, ch.index, ch.text)
            meta = {**metadata, "section": ch.section}
            all_chunks.append(StoredChunk(cid, doc_id, ch.text, meta))
            texts.append(ch.text)

    if not all_chunks:
        return IngestResult(len(documents), 0, 0)

    vectors = embedder.encode(texts)
    added = store.upsert(collection, all_chunks, vectors)
    return IngestResult(
        n_documents=len(documents),
        n_chunks=added,
        n_skipped_idempotent=len(all_chunks) - added,
    )


def search_documents(
    query: str, collection: str, top_k: int, embedder: Embedder, store: VectorStore
) -> list[Hit]:
    qvec = embedder.encode([query])[0]
    return store.search(collection, qvec, top_k)
