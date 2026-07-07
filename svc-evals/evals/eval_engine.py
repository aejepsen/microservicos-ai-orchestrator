"""G2 — correção do motor de gate: PASS/FAIL certos, incluindo bordas (valor==threshold)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evals_svc.gate import evaluate_gate  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"

# (valor, comparador, threshold, esperado)
CASES = [
    (0.90, ">=", 0.90, True),   # borda
    (0.899, ">=", 0.90, False),
    (0.91, ">=", 0.90, True),
    (0.90, ">", 0.90, False),   # borda estrita
    (0.91, ">", 0.90, True),
    (0.90, "<=", 0.90, True),   # borda
    (0.90, "<", 0.90, False),   # borda estrita
    (0.89, "<", 0.90, True),
    (0.90, "==", 0.90, True),
    (0.9000001, "==", 0.90, False),
]


def main() -> int:
    wrong = []
    for value, comp, thr, expected in CASES:
        got = evaluate_gate(value, comp, thr)
        if got != expected:
            wrong.append((value, comp, thr, expected, got))
    ok = not wrong
    print(f"[G2] casos={len(CASES)} errados={len(wrong)} -> {'PASS' if ok else 'FAIL'}")
    for w in wrong:
        print(f"      ERRO valor={w[0]} {w[1]} {w[2]} esperado={w[3]} obtido={w[4]}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"engine_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        f'{{"source":"eval","cases":{len(CASES)},"wrong":{len(wrong)},"pass":{str(ok).lower()}}}'
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
