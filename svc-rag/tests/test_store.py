from __future__ import annotations

import numpy as np

from rag_svc.store import InMemoryStore, StoredChunk, chunk_id


def _chunk(cid: str) -> StoredChunk:
    return StoredChunk(cid, "d1", f"texto {cid}", {})


def test_chunk_id_deterministic() -> None:
    assert chunk_id("d", 0, "abc") == chunk_id("d", 0, "abc")


def test_chunk_id_changes_with_content() -> None:
    assert chunk_id("d", 0, "abc") != chunk_id("d", 0, "abd")


def test_upsert_and_count() -> None:
    s = InMemoryStore()
    added = s.upsert("c", [_chunk("a"), _chunk("b")], np.array([[1.0, 0.0], [0.0, 1.0]]))
    assert added == 2 and s.count("c") == 2


def test_idempotent_upsert() -> None:
    s = InMemoryStore()
    vecs = np.array([[1.0, 0.0]])
    s.upsert("c", [_chunk("a")], vecs)
    added = s.upsert("c", [_chunk("a")], vecs)
    assert added == 0 and s.count("c") == 1


def test_search_ranks_by_cosine() -> None:
    s = InMemoryStore()
    s.upsert("c", [_chunk("a"), _chunk("b")], np.array([[1.0, 0.0], [0.0, 1.0]]))
    hits = s.search("c", np.array([1.0, 0.1]), 2)
    assert hits[0].chunk_id == "a"
    assert hits[0].score >= hits[1].score


def test_collections_listed() -> None:
    s = InMemoryStore()
    s.upsert("x", [_chunk("a")], np.array([[1.0, 0.0]]))
    s.upsert("y", [_chunk("b")], np.array([[0.0, 1.0]]))
    assert set(s.collections()) == {"x", "y"}


def test_search_empty_collection() -> None:
    assert InMemoryStore().search("nada", np.array([1.0]), 3) == []
