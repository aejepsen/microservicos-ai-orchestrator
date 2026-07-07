"""G8 — overhead de busca (FakeEmbedder + InMemory): P95 < 80 ms."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_svc.embedder import FakeEmbedder  # noqa: E402
from rag_svc.ingest import ingest_documents, search_documents  # noqa: E402
from rag_svc.store import InMemoryStore  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
GATE_MS = 80.0


def main() -> int:
    emb = FakeEmbedder()
    store = InMemoryStore()
    docs = [{"id": f"d{i}", "text": f"# S{i}\n\ndocumento numero {i} com conteudo variado sobre topico {i%7}"}
            for i in range(200)]
    ingest_documents(docs, "c", emb, store, max_chars=800, overlap=100)

    for _ in range(10):
        search_documents("documento topico 3", "c", 3, emb, store)

    lat = []
    for _ in range(200):
        start = time.perf_counter()
        search_documents("documento topico 3", "c", 3, emb, store)
        lat.append((time.perf_counter() - start) * 1000.0)

    lat.sort()
    p50 = statistics.median(lat)
    p95 = lat[int(len(lat) * 0.95) - 1]
    ok = p95 < GATE_MS
    print(f"[G8] busca n=200 (corpus 200) P50={p50:.2f}ms P95={p95:.2f}ms (gate < {GATE_MS}ms) -> {'PASS' if ok else 'FAIL'}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"bench_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "p50_ms": p50, "p95_ms": p95, "pass": ok})
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
