"""Runner: carrega casos, obtém respostas (offline/live), aplica scorer, gateia."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evals_svc.gate import evaluate_gate
from evals_svc.jsonpath import extract
from evals_svc.scorers import Case, ScoreResult, aggregate, get_scorer


@dataclass(frozen=True)
class RunOutcome:
    metric: str
    value: float
    passed: bool | None
    n_cases: int
    n_failed_cases: int
    per_case: list[dict[str, Any]]


def _response_offline(case: Case) -> Any:
    if "response" not in case:
        raise ValueError("modo offline exige campo 'response' em cada caso")
    return case["response"]


def run_suite(
    cases: list[Case],
    scorer_name: str,
    scorer_params: dict[str, Any],
    gate: dict[str, Any] | None,
    response_fn: Any = _response_offline,
) -> RunOutcome:
    """response_fn(case) -> resposta_obtida. Default: modo offline (lê do golden)."""
    if not cases:
        raise ValueError("golden vazio")
    scorer = get_scorer(scorer_name)
    results: list[ScoreResult] = []
    per_case: list[dict[str, Any]] = []
    for case in cases:
        response = response_fn(case)
        res = scorer(case, response, scorer_params)
        results.append(res)
        per_case.append({"passed": res.passed, "score": res.score, "trap": case.get("trap", False)})

    metric = aggregate(scorer_name, cases, results)
    passed: bool | None = None
    if gate is not None:
        passed = evaluate_gate(metric.value, gate["comparator"], float(gate["threshold"]))
    return RunOutcome(
        metric=metric.metric,
        value=metric.value,
        passed=passed,
        n_cases=metric.n_cases,
        n_failed_cases=metric.n_failed_cases,
        per_case=per_case,
    )


def live_response_fn(target: dict[str, Any], deadline_s: float) -> Any:
    """Fábrica de response_fn para modo live: chama o endpoint do alvo por caso."""
    import httpx

    def _fn(case: Case) -> Any:
        payload = {target["input_field"]: case.get("input")}
        method = target.get("method", "POST").upper()
        with httpx.Client(timeout=deadline_s) as client:
            resp = client.request(method, target["url"], json=payload)
            resp.raise_for_status()
            return extract(resp.json(), target["output_pointer"])

    return _fn
