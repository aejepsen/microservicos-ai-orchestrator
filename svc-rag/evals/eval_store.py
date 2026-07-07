"""G4 — vector store: ranking cosseno correto + ingestão idempotente."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_svc.embedder import FakeEmbedder  # noqa: E402
from rag_svc.ingest import ingest_documents, search_documents  # noqa: E402
from rag_svc.store import InMemoryStore  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"

DOCS = [
    {"id": "d1", "text": "# A\n\ngato preto dorme no telhado quente"},
    {"id": "d2", "text": "# B\n\ncachorro late no quintal grande"},
    {"id": "d3", "text": "# C\n\ncarro vermelho corre na estrada"},
]


def main() -> int:
    checks: list[tuple[str, bool]] = []
    emb = FakeEmbedder()
    store = InMemoryStore()

    r1 = ingest_documents(DOCS, "c", emb, store, max_chars=800, overlap=100)
    checks.append(("ingest_3_chunks", r1.n_chunks == 3))

    # Reingestão idempotente: mesmo conteúdo -> 0 novos, 3 skipped.
    r2 = ingest_documents(DOCS, "c", emb, store, max_chars=800, overlap=100)
    checks.append(("idempotente", r2.n_chunks == 0 and r2.n_skipped_idempotent == 3))
    checks.append(("count_estavel", store.count("c") == 3))

    # Ranking: query sobre 'gato telhado' traz d1 no topo.
    hits = search_documents("gato telhado", "c", 3, emb, store)
    checks.append(("ranking_relevante_topo", hits[0].doc_id == "d1"))
    checks.append(("scores_desc", all(hits[i].score >= hits[i+1].score for i in range(len(hits)-1))))

    wrong = [n for n, ok in checks if not ok]
    ok = not wrong
    print(f"[G4] checks={len(checks)} divergencias={len(wrong)} -> {'PASS' if ok else 'FAIL'}")
    for w in wrong:
        print(f"      DIVERGENCIA {w}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"store_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "checks": len(checks), "wrong": len(wrong), "pass": ok})
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
