"""G4 — OOD: AUC >= 0.95 via protocolo LOO (fit real do OodGuard).

Uso: python evals/eval_ood.py  (exit 0 se PASS; 1 se FAIL)
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from guardrails.config import load_settings  # noqa: E402
from guardrails.ood import OodGuard, SbertEmbedder  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
RESULTS = Path(__file__).resolve().parent / "results"
AUC_GATE = 0.95


def _load(name: str) -> list[str]:
    return [json.loads(ln)["text"] for ln in (DATA / name).read_text().splitlines() if ln.strip()]


def main() -> int:
    in_domain = _load("ood_in_domain.jsonl")
    out = _load("ood_out.jsonl")
    embedder = SbertEmbedder(load_settings().embed_model)

    with tempfile.TemporaryDirectory() as tmp:
        guard = OodGuard(tmp)
        report = guard.fit(
            [{"text": t, "is_clarification": False} for t in in_domain], out, embedder
        )

    passed = report.auc_loo >= AUC_GATE and len(in_domain) >= 30 and len(out) >= 30
    print(f"[G4] in={len(in_domain)} out={len(out)} n_fit={report.n_samples} "
          f"threshold={report.threshold:.4f} AUC_LOO={report.auc_loo:.4f} "
          f"(gate >= {AUC_GATE}) -> {'PASS' if passed else 'FAIL'}")

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"ood_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps(
            {"source": "eval", "n_in": len(in_domain), "n_out": len(out),
             "threshold": report.threshold, "auc_loo": report.auc_loo, "pass": passed},
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
