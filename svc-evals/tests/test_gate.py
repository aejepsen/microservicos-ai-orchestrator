from __future__ import annotations

import pytest

from evals_svc.gate import evaluate_gate


@pytest.mark.parametrize(
    "value,comp,thr,expected",
    [
        (0.90, ">=", 0.90, True),
        (0.899, ">=", 0.90, False),
        (0.90, ">", 0.90, False),
        (0.91, ">", 0.90, True),
        (0.90, "<=", 0.90, True),
        (0.90, "<", 0.90, False),
        (0.89, "<", 0.90, True),
        (0.90, "==", 0.90, True),
    ],
)
def test_gate_boundaries(value: float, comp: str, thr: float, expected: bool) -> None:
    assert evaluate_gate(value, comp, thr) is expected


def test_invalid_comparator() -> None:
    with pytest.raises(ValueError, match="comparador"):
        evaluate_gate(1.0, "~=", 0.5)
