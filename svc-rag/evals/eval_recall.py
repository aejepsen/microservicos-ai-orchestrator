"""G2 — Recall@3 com SBERT real + InMemoryStore (gate LENTO, sem Qdrant)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_svc.config import load_settings  # noqa: E402
from rag_svc.embedder import SbertEmbedder  # noqa: E402
from rag_svc.ingest import ingest_documents, search_documents  # noqa: E402
from rag_svc.store import InMemoryStore  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
RESULTS = Path(__file__).resolve().parent / "results"
RECALL_GATE = 0.80
TOP_K = 3


def _load(name: str) -> list[dict]:
    return [json.loads(ln) for ln in (DATA / name).read_text().splitlines() if ln.strip()]


def main() -> int:
    docs = _load("corpus.jsonl")
    queries = _load("golden_recall.jsonl")
    embedder = SbertEmbedder(load_settings().embed_model)
    store = InMemoryStore()
    ingest_documents(docs, "default", embedder, store, max_chars=800, overlap=100)

    hits = 0
    misses = []
    for q in queries:
        found = search_documents(q["query"], "default", TOP_K, embedder, store)
        doc_ids = [h.doc_id for h in found]
        if q["expected"] in doc_ids:
            hits += 1
        else:
            misses.append((q["query"][:45], q["expected"], doc_ids))
    recall = hits / len(queries) if queries else 0.0
    ok = recall >= RECALL_GATE

    print(f"[G2] queries={len(queries)} recall@{TOP_K}={recall:.3f} (gate >= {RECALL_GATE}) -> {'PASS' if ok else 'FAIL'}")
    for m in misses:
        print(f"      MISS exp={m[1]} got={m[2]} :: {m[0]}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"recall_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "n": len(queries), "recall_at_3": recall, "pass": ok}, indent=2)
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
