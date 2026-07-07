"""G3 — fusão RRF + seleção de camada (determinístico, sem modelo)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from router_svc.bm25 import ranks_from_scores, rrf_fuse  # noqa: E402
from router_svc.embedder import FakeEmbedder  # noqa: E402
from router_svc.router import Router  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"


def main() -> int:
    checks: list[tuple[str, bool]] = []

    # RRF à mão: dense ranks [1,2,3], lexical ranks [3,1,2], k=60.
    dense = [0.9, 0.5, 0.1]  # ranks 1,2,3
    lexical = [0.1, 0.9, 0.5]  # ranks 3,1,2
    fused = rrf_fuse(ranks_from_scores(dense), ranks_from_scores(lexical), 60)
    expected = [1/61 + 1/63, 1/62 + 1/61, 1/63 + 1/62]
    checks.append(("rrf_values", all(abs(a - b) < 1e-9 for a, b in zip(fused, expected, strict=True))))
    checks.append(("rrf_winner_doc1", max(range(3), key=lambda i: fused[i]) == 1))  # doc idx 1

    checks.append(("ranks_base1", ranks_from_scores([0.1, 0.9, 0.5]) == [3, 1, 2]))

    # Seleção de camada com FakeEmbedder: threshold alto -> nunca semantic; baixo -> semantic.
    routes = [("a", ["alpha um", "alpha dois"]), ("b", ["beta um", "beta dois"])]
    r_low = Router(routes, FakeEmbedder(), threshold=-1.0, tie_margin=0.05, rrf_k=60, hybrid=True)
    plan_low = r_low.route("alpha um", allow_llm=False, llm=None, soft_fallback=True)
    checks.append(("low_threshold_semantic", plan_low.layer == "semantic"))

    r_high = Router(routes, FakeEmbedder(), threshold=1.1, tie_margin=0.05, rrf_k=60, hybrid=True)
    plan_high = r_high.route("xyz sem guard", allow_llm=False, llm=None, soft_fallback=True)
    checks.append(("high_threshold_fallback", plan_high.layer == "fallback"))

    wrong = [n for n, ok in checks if not ok]
    ok = not wrong
    print(f"[G3] checks={len(checks)} divergencias={len(wrong)} -> {'PASS' if ok else 'FAIL'}")
    for w in wrong:
        print(f"      DIVERGENCIA {w}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"fusion_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "checks": len(checks), "wrong": len(wrong), "pass": ok})
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
