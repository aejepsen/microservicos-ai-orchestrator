from __future__ import annotations

from rag_svc.chunking import chunk_document


def test_sections_split() -> None:
    doc = "# A\n\ncorpo a\n\n## B\n\ncorpo b"
    chunks = chunk_document(doc)
    sections = {c.section for c in chunks}
    assert "A" in sections and "B" in sections


def test_header_in_code_fence_ignored() -> None:
    doc = "# Real\n\ntexto\n\n```\n# fake header\ncode\n```"
    sections = {c.section for c in chunk_document(doc)}
    assert "Real" in sections
    assert "fake header" not in sections


def test_no_content_loss() -> None:
    doc = "# S\n\numa frase importante aqui"
    joined = " ".join(c.text for c in chunk_document(doc))
    assert "uma frase importante aqui" in joined


def test_size_split_multiple_chunks() -> None:
    doc = "# S\n\n" + ("palavra " * 300)
    chunks = chunk_document(doc, max_chars=200, overlap=40)
    assert len(chunks) > 1


def test_no_word_cut() -> None:
    doc = "# S\n\n" + ("palavra " * 300)
    for c in chunk_document(doc, max_chars=200, overlap=40):
        assert not c.text.endswith("palavr")
        assert len(c.text) <= 200


def test_empty_body_skipped() -> None:
    assert chunk_document("# só header\n") == []


def test_index_monotonic() -> None:
    doc = "# A\n\n" + ("x " * 300) + "\n\n# B\n\ncorpo"
    idxs = [c.index for c in chunk_document(doc, max_chars=200, overlap=20)]
    assert idxs == sorted(idxs)
