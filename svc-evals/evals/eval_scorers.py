"""G3 — correção dos scorers: recall@k, F1/accuracy, match batem valores à mão."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evals_svc.runner import run_suite  # noqa: E402
from evals_svc.scorers import (  # noqa: E402
    score_classification,
    score_contains,
    score_exact_match,
    score_recall_at_k,
    score_regex_match,
)

DATA = Path(__file__).resolve().parent / "data"
RESULTS = Path(__file__).resolve().parent / "results"


def _load(name: str) -> list[dict]:
    return [json.loads(ln) for ln in (DATA / name).read_text().splitlines() if ln.strip()]


def main() -> int:
    checks: list[tuple[str, bool]] = []

    # Unitários de match (valores à mão).
    checks.append(("exact_hit", score_exact_match({"expected": "a"}, "a", {}).passed))
    checks.append(("exact_miss", not score_exact_match({"expected": "a"}, "b", {}).passed))
    checks.append(("contains_hit", score_contains({"expected": "fato"}, "tem fato aqui", {}).passed))
    # ARMADILHA: contains marcaria hit por acaso? rótulo negativo — expected ausente na resposta
    checks.append(("contains_trap", not score_contains({"expected": "xyz"}, "abc def", {}).passed))
    checks.append(("regex_hit", score_regex_match({"expected": r"\d{3}"}, "sku 123", {}).passed))
    checks.append(("recall_hit", score_recall_at_k({"expected": "x"}, ["a", "x", "b"], {"k": 3}).passed))
    checks.append(("recall_miss_out_of_k", not score_recall_at_k({"expected": "x"}, ["a", "b", "c", "x"], {"k": 3}).passed))
    checks.append(("classif_hit", score_classification({"expected": "rh"}, "RH", {}).passed))

    # recall@3 agregado sobre golden (5 hits / 6 = 0.8333).
    recall_out = run_suite(_load("golden_recall.jsonl"), "recall_at_k", {"k": 3}, None)
    checks.append(("recall_agg_0.833", abs(recall_out.value - 0.8333) < 0.001))

    # classification agregada: 10/10 corretos -> macro_f1 = 1.0.
    routing_out = run_suite(_load("golden_routing.jsonl"), "classification", {}, None)
    checks.append(("routing_f1_1.0", abs(routing_out.value - 1.0) < 1e-9))

    wrong = [name for name, ok in checks if not ok]
    ok = not wrong
    print(f"[G3] checks={len(checks)} divergencias={len(wrong)} -> {'PASS' if ok else 'FAIL'}")
    for w in wrong:
        print(f"      DIVERGENCIA {w}")
    print(f"      recall@3={recall_out.value} routing_macro_f1={routing_out.value}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"scorers_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "checks": len(checks), "wrong": len(wrong),
                    "recall_at_3": recall_out.value, "routing_macro_f1": routing_out.value,
                    "pass": ok}, indent=2)
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
