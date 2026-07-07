"""G8 — overhead do /v1/overview (cache/agregação em memória): P95 < 40 ms."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from obs_svc.app import State, create_app  # noqa: E402
from obs_svc.config import Settings  # noqa: E402
from obs_svc.scraper import FakeScraper  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
GATE_MS = 40.0

PAYLOADS = {u: {"source": "live", "requests_total": i, "latency_ms_p95": 5.0}
            for i, u in enumerate(["svc-guardrails", "svc-evals", "svc-inference", "svc-router", "svc-rag"])}


def main() -> int:
    s = Settings(internal_key="b", allow_local_upstream=True, rate_limit_per_min=1000000)
    st = State(s, FakeScraper(PAYLOADS))
    st.agg.refresh()
    c = TestClient(create_app(settings=s, state=st))
    h = {"X-Internal-Key": "b"}

    for _ in range(10):
        c.get("/v1/overview", headers=h)

    lat = []
    for _ in range(200):
        start = time.perf_counter()
        c.get("/v1/overview", headers=h)
        lat.append((time.perf_counter() - start) * 1000.0)

    lat.sort()
    p50 = statistics.median(lat)
    p95 = lat[int(len(lat) * 0.95) - 1]
    ok = p95 < GATE_MS
    print(f"[G8] overview n=200 P50={p50:.2f}ms P95={p95:.2f}ms (gate < {GATE_MS}ms) -> {'PASS' if ok else 'FAIL'}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"bench_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "p50_ms": p50, "p95_ms": p95, "pass": ok})
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
