"""Suites registradas em código. Cada uma: golden + scorer + gate + source default."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parents[2] / "evals" / "data"


@dataclass(frozen=True)
class Suite:
    name: str
    golden: str  # arquivo JSONL em evals/data
    scorer: str
    scorer_params: dict[str, Any]
    gate: dict[str, Any] | None
    metric: str
    source: str = "eval"


# Suites de dogfood + exemplos reproduzindo baselines do AIO.
REGISTRY: dict[str, Suite] = {
    "recall_at_3": Suite(
        name="recall_at_3",
        golden="golden_recall.jsonl",
        scorer="recall_at_k",
        scorer_params={"k": 3},
        gate={"comparator": ">=", "threshold": 0.80},
        metric="recall_at_k",
    ),
    "routing_accuracy": Suite(
        name="routing_accuracy",
        golden="golden_routing.jsonl",
        scorer="classification",
        scorer_params={},
        gate={"comparator": ">=", "threshold": 0.90},
        metric="macro_f1",
    ),
}


def list_suites() -> list[Suite]:
    return list(REGISTRY.values())


def get_suite(name: str) -> Suite | None:
    return REGISTRY.get(name)
