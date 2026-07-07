"""G8 — perf: /v1/results P95 < 50 ms; runner 100 casos P95 < 300 ms."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evals_svc.runner import run_suite  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
RESULTS_GATE_MS = 50.0
RUNNER_GATE_MS = 300.0


def main() -> int:
    import tempfile

    from fastapi.testclient import TestClient

    from evals_svc.app import create_app
    from evals_svc.config import Settings

    tmp = tempfile.mkdtemp()
    settings = Settings(internal_key="bench", rate_limit_per_min=100000, results_dir=tmp)
    client = TestClient(create_app(settings=settings))
    headers = {"X-Internal-Key": "bench"}

    # Popula uma rodada para /v1/results ter conteúdo.
    client.post("/v1/run", json={"suite": "routing_accuracy"}, headers=headers)

    lat_results = []
    for _ in range(100):
        s = time.perf_counter()
        client.get("/v1/results", headers=headers)
        lat_results.append((time.perf_counter() - s) * 1000.0)

    # Runner offline sobre 100 casos.
    cases = [{"expected": "a", "response": "a"} for _ in range(100)]
    lat_runner = []
    for _ in range(50):
        s = time.perf_counter()
        run_suite(cases, "exact_match", {}, {"comparator": ">=", "threshold": 0.9})
        lat_runner.append((time.perf_counter() - s) * 1000.0)

    lat_results.sort()
    lat_runner.sort()
    p95_r = lat_results[int(len(lat_results) * 0.95) - 1]
    p95_run = lat_runner[int(len(lat_runner) * 0.95) - 1]
    ok = p95_r < RESULTS_GATE_MS and p95_run < RUNNER_GATE_MS
    print(f"[G8] /v1/results P95={p95_r:.1f}ms (<{RESULTS_GATE_MS}) | runner100 P95={p95_run:.1f}ms (<{RUNNER_GATE_MS}) -> {'PASS' if ok else 'FAIL'}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"bench_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "results_p95_ms": p95_r, "runner_p95_ms": p95_run,
                    "p50_results_ms": statistics.median(lat_results), "pass": ok}, indent=2)
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
