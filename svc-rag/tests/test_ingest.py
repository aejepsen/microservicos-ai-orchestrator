from __future__ import annotations

from rag_svc.embedder import FakeEmbedder
from rag_svc.ingest import ingest_documents, search_documents
from rag_svc.store import InMemoryStore

DOCS = [
    {"id": "reembolso", "text": "# Reembolso\n\nDespesas de viagem reembolsadas em 30 dias."},
    {"id": "ferias", "text": "# Férias\n\nDireito a férias após 12 meses de trabalho."},
    {"id": "distrator", "text": "# Viagem\n\nViagens de integração anuais votadas pela equipe."},
]


def test_ingest_counts() -> None:
    r = ingest_documents(DOCS, "c", FakeEmbedder(), InMemoryStore(), max_chars=800, overlap=100)
    assert r.n_documents == 3 and r.n_chunks == 3


def test_ingest_idempotent() -> None:
    emb, store = FakeEmbedder(), InMemoryStore()
    ingest_documents(DOCS, "c", emb, store, max_chars=800, overlap=100)
    r2 = ingest_documents(DOCS, "c", emb, store, max_chars=800, overlap=100)
    assert r2.n_chunks == 0 and r2.n_skipped_idempotent == 3


def test_search_returns_relevant() -> None:
    emb, store = FakeEmbedder(), InMemoryStore()
    ingest_documents(DOCS, "c", emb, store, max_chars=800, overlap=100)
    hits = search_documents("reembolso de viagem despesas", "c", 3, emb, store)
    assert hits[0].doc_id == "reembolso"


def test_search_metadata_has_section() -> None:
    emb, store = FakeEmbedder(), InMemoryStore()
    ingest_documents(DOCS, "c", emb, store, max_chars=800, overlap=100)
    hits = search_documents("férias trabalho", "c", 1, emb, store)
    assert "section" in hits[0].metadata


def test_empty_doc_no_chunks() -> None:
    r = ingest_documents([{"id": "x", "text": "# só header"}], "c", FakeEmbedder(), InMemoryStore(), max_chars=800, overlap=100)
    assert r.n_chunks == 0
