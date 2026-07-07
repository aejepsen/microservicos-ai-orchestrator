"""Motor de gate: comparador + threshold → PASS/FAIL. Bordas explícitas."""

from __future__ import annotations

import operator
from collections.abc import Callable

_COMPARATORS: dict[str, Callable[[float, float], bool]] = {
    ">=": operator.ge,
    ">": operator.gt,
    "<=": operator.le,
    "<": operator.lt,
    "==": operator.eq,
}


def evaluate_gate(value: float, comparator: str, threshold: float) -> bool:
    if comparator not in _COMPARATORS:
        raise ValueError(f"comparador invalido: {comparator}")
    return _COMPARATORS[comparator](value, threshold)
