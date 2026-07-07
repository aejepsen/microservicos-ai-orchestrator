"""G8 — overhead da fachada: P95 < 30 ms no chat não-streaming (FakeBackend)."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from inference.app import State, create_app  # noqa: E402
from inference.backends import FakeBackend  # noqa: E402
from inference.config import Settings  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
GATE_MS = 30.0


def main() -> int:
    s = Settings(internal_key="k", backend="fake", rate_limit_per_min=1000000)
    c = TestClient(create_app(settings=s, state=State(s, FakeBackend())))
    h = {"X-Internal-Key": "k"}
    body = {"model": "fake-model", "messages": [{"role": "user", "content": "oi"}]}

    for _ in range(10):
        c.post("/v1/chat/completions", json=body, headers=h)

    lat = []
    for _ in range(200):
        start = time.perf_counter()
        c.post("/v1/chat/completions", json=body, headers=h)
        lat.append((time.perf_counter() - start) * 1000.0)

    lat.sort()
    p50 = statistics.median(lat)
    p95 = lat[int(len(lat) * 0.95) - 1]
    ok = p95 < GATE_MS
    print(f"[G8] overhead fachada n=200 P50={p50:.2f}ms P95={p95:.2f}ms (gate < {GATE_MS}ms) -> {'PASS' if ok else 'FAIL'}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"bench_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "p50_ms": p50, "p95_ms": p95, "pass": ok})
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
