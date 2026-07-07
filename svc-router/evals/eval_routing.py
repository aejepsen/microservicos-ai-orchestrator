"""G2 — acurácia de roteamento com SBERT real sobre golden (gate LENTO)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from router_svc.config import load_settings  # noqa: E402
from router_svc.embedder import SbertEmbedder  # noqa: E402
from router_svc.router import Router  # noqa: E402
from router_svc.routes import registry  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
RESULTS = Path(__file__).resolve().parent / "results"
ACC_GATE = 0.85


def main() -> int:
    cases = [json.loads(ln) for ln in (DATA / "golden_routing.jsonl").read_text().splitlines() if ln.strip()]
    settings = load_settings()
    embedder = SbertEmbedder(settings.embed_model)
    router = Router(
        [(r.name, r.exemplars) for r in registry()], embedder,
        threshold=settings.route_threshold, tie_margin=settings.tie_margin,
        rrf_k=settings.rrf_k, hybrid=settings.hybrid_enabled,
    )

    hits = 0
    misses = []
    for c in cases:
        # allow_llm=False + soft: mede só semântica+guards (sem LLM externo).
        plan = router.route(c["query"], allow_llm=False, llm=None, soft_fallback=True)
        if c["expected"] in plan.domains:
            hits += 1
        else:
            misses.append((c["query"][:50], c["expected"], plan.domains, plan.layer))
    acc = hits / len(cases) if cases else 0.0
    ok = acc >= ACC_GATE

    print(f"[G2] casos={len(cases)} acuracia={acc:.3f} (gate >= {ACC_GATE}) -> {'PASS' if ok else 'FAIL'}")
    for m in misses:
        print(f"      MISS exp={m[1]} got={m[2]} ({m[3]}) :: {m[0]}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"routing_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "n": len(cases), "accuracy": acc, "pass": ok}, indent=2)
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
