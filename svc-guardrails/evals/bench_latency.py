"""G8 — latência: P95 < 150 ms no /v1/analyze completo (CPU).

Mede o caminho de análise direto (sem overhead HTTP), com OOD fitado.
Uso: python evals/bench_latency.py  (exit 0 se PASS; 1 se FAIL)
"""

from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from guardrails.config import load_settings  # noqa: E402
from guardrails.injection import detect_injection  # noqa: E402
from guardrails.ood import OodGuard, SbertEmbedder  # noqa: E402
from guardrails.sanitize import sanitize  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
RESULTS = Path(__file__).resolve().parent / "results"
P95_GATE_MS = 150.0


def main() -> int:
    in_domain = [json.loads(ln)["text"] for ln in (DATA / "ood_in_domain.jsonl").read_text().splitlines() if ln.strip()]
    out = [json.loads(ln)["text"] for ln in (DATA / "ood_out.jsonl").read_text().splitlines() if ln.strip()]
    embedder = SbertEmbedder(load_settings().embed_model)
    sample = "Qual o saldo da conta a pagar numero 231 deste mes?"

    with tempfile.TemporaryDirectory() as tmp:
        guard = OodGuard(tmp)
        guard.fit([{"text": t} for t in in_domain], out, embedder)

        for _ in range(5):  # warm-up
            guard.check(sample, embedder)

        lat = []
        for _ in range(100):
            start = time.perf_counter()
            s, _a = sanitize(sample)
            detect_injection(sample)
            guard.check(s, embedder)
            lat.append((time.perf_counter() - start) * 1000.0)

    lat.sort()
    p50 = statistics.median(lat)
    p95 = lat[int(len(lat) * 0.95) - 1]
    passed = p95 < P95_GATE_MS
    print(f"[G8] n=100 P50={p50:.1f}ms P95={p95:.1f}ms (gate < {P95_GATE_MS}ms) -> {'PASS' if passed else 'FAIL'}")

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"bench_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "p50_ms": p50, "p95_ms": p95, "pass": passed}, indent=2)
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
