"""G4 — judge determinístico (fake), faithfulness 97.5% reproduzida, parse robusto."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evals_svc.judge import FakeJudge, parse_verdict, score_llm_judge  # noqa: E402
from evals_svc.runner import run_suite  # noqa: E402
from evals_svc.scorers import SCORERS  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
RESULTS = Path(__file__).resolve().parent / "results"
FAITHFUL_GATE = 0.90


def _load(name: str) -> list[dict]:
    return [json.loads(ln) for ln in (DATA / name).read_text().splitlines() if ln.strip()]


def main() -> int:
    checks: list[tuple[str, bool]] = []
    judge = FakeJudge()

    # Determinismo: mesma entrada, mesmo veredito, 5x.
    prompt = "EVIDENCIA: fato1\nRESPOSTA: tem fato1 aqui"
    verdicts = {json.dumps(judge.judge(prompt), sort_keys=True) for _ in range(5)}
    checks.append(("determinismo", len(verdicts) == 1))

    # Parse robusto: JSON sujo com texto em volta.
    parsed = parse_verdict('bla bla {"faithful": true} fim')
    checks.append(("parse_sujo", parsed.get("faithful") is True))

    # Faithfulness agregada sobre golden-espelho: 39/40 = 0.975.
    SCORERS["llm_judge"] = score_llm_judge
    out = run_suite(
        _load("golden_faithfulness.jsonl"), "llm_judge", {"_judge": judge},
        {"comparator": ">=", "threshold": FAITHFUL_GATE},
    )
    checks.append(("faithfulness_0.975", abs(out.value - 0.975) < 0.001))
    checks.append(("gate_pass", out.passed is True))

    wrong = [n for n, ok in checks if not ok]
    ok = not wrong
    print(f"[G4] checks={len(checks)} divergencias={len(wrong)} faithfulness={out.value} -> {'PASS' if ok else 'FAIL'}")
    for w in wrong:
        print(f"      DIVERGENCIA {w}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"judge_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "checks": len(checks), "wrong": len(wrong),
                    "faithfulness": out.value, "pass": ok}, indent=2)
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
