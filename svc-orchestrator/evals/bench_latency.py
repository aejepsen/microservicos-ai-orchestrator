"""G8 — overhead de orquestração (downstreams fake): P95 < 50 ms, single-domínio."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from orch_svc.app import State, create_app  # noqa: E402
from orch_svc.clients import FakeGuardrails, FakeInference, FakeRag, FakeRouter  # noqa: E402
from orch_svc.config import Settings  # noqa: E402
from orch_svc.orchestrator import Breakers, Orchestrator  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
GATE_MS = 50.0


def main() -> int:
    s = Settings(internal_key="b", allow_local_downstream=True, rate_limit_per_min=1000000)
    st = State(s, Orchestrator(
        FakeGuardrails(), FakeRouter(["financas"]), FakeRag(), FakeInference(),
        Breakers(3, 30), hitl_enabled=False,
    ))
    c = TestClient(create_app(settings=s, state=st))
    h = {"X-Internal-Key": "b"}
    body = {"query": "qual o saldo da conta?"}

    for _ in range(10):
        c.post("/v1/chat", json=body, headers=h)

    lat = []
    for _ in range(200):
        start = time.perf_counter()
        c.post("/v1/chat", json=body, headers=h)
        lat.append((time.perf_counter() - start) * 1000.0)

    lat.sort()
    p50 = statistics.median(lat)
    p95 = lat[int(len(lat) * 0.95) - 1]
    ok = p95 < GATE_MS
    print(f"[G8] orquestracao n=200 P50={p50:.2f}ms P95={p95:.2f}ms (gate < {GATE_MS}ms) -> {'PASS' if ok else 'FAIL'}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"bench_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "p50_ms": p50, "p95_ms": p95, "pass": ok})
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
