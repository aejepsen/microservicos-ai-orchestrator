"""G8 — overhead de roteamento (FakeEmbedder): P95 < 60 ms, só fusão/guards."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from router_svc.embedder import FakeEmbedder  # noqa: E402
from router_svc.router import Router  # noqa: E402
from router_svc.routes import registry  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
GATE_MS = 60.0


def main() -> int:
    router = Router(
        [(r.name, r.exemplars) for r in registry()], FakeEmbedder(),
        threshold=0.45, tie_margin=0.05, rrf_k=60, hybrid=True,
    )
    query = "Qual o saldo da conta a pagar 231 deste mes?"

    for _ in range(10):
        router.route(query, allow_llm=False, llm=None, soft_fallback=True)

    lat = []
    for _ in range(300):
        start = time.perf_counter()
        router.route(query, allow_llm=False, llm=None, soft_fallback=True)
        lat.append((time.perf_counter() - start) * 1000.0)

    lat.sort()
    p50 = statistics.median(lat)
    p95 = lat[int(len(lat) * 0.95) - 1]
    ok = p95 < GATE_MS
    print(f"[G8] overhead roteamento n=300 P50={p50:.2f}ms P95={p95:.2f}ms (gate < {GATE_MS}ms) -> {'PASS' if ok else 'FAIL'}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"bench_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "p50_ms": p50, "p95_ms": p95, "pass": ok})
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
