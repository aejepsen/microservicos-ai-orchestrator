"""Scorers built-in + métricas de agregação.

Um scorer é uma função pura (caso, resposta_obtida, params) -> ScoreResult.
A resposta_obtida vem do golden (modo offline) ou do alvo HTTP (modo live).
Nenhum scorer executa conteúdo do golden — apenas compara valores.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Case = dict[str, Any]


@dataclass(frozen=True)
class ScoreResult:
    passed: bool
    score: float


@dataclass(frozen=True)
class MetricResult:
    metric: str
    value: float
    n_cases: int
    n_failed_cases: int


# --- scorers por-caso -------------------------------------------------------

def _expected(case: Case) -> Any:
    return case.get("expected")


def score_exact_match(case: Case, response: Any, params: dict[str, Any]) -> ScoreResult:
    ok = str(response).strip() == str(_expected(case)).strip()
    return ScoreResult(ok, 1.0 if ok else 0.0)


def score_contains(case: Case, response: Any, params: dict[str, Any]) -> ScoreResult:
    ok = str(_expected(case)) in str(response)
    return ScoreResult(ok, 1.0 if ok else 0.0)


def score_regex_match(case: Case, response: Any, params: dict[str, Any]) -> ScoreResult:
    pattern = str(case.get("expected", params.get("pattern", "")))
    ok = re.search(pattern, str(response)) is not None
    return ScoreResult(ok, 1.0 if ok else 0.0)


def score_numeric_threshold(case: Case, response: Any, params: dict[str, Any]) -> ScoreResult:
    try:
        val = float(response)
    except (TypeError, ValueError):
        return ScoreResult(False, 0.0)
    target = float(_expected(case))
    tol = float(params.get("tolerance", 0.0))
    ok = abs(val - target) <= tol
    return ScoreResult(ok, 1.0 if ok else 0.0)


def score_recall_at_k(case: Case, response: Any, params: dict[str, Any]) -> ScoreResult:
    """expected = item(s) relevante(s); response = lista ranqueada. Hit se relevante em top-k."""
    k = int(params.get("k", 3))
    expected = _expected(case)
    relevant = set(expected if isinstance(expected, list) else [expected])
    retrieved = list(response)[:k] if isinstance(response, (list, tuple)) else [response]
    hit = any(r in relevant for r in retrieved)
    return ScoreResult(hit, 1.0 if hit else 0.0)


def score_classification(case: Case, response: Any, params: dict[str, Any]) -> ScoreResult:
    """Rótulo predito vs esperado. Métrica agregada (accuracy+F1) calculada no agregador."""
    ok = str(response).strip().lower() == str(_expected(case)).strip().lower()
    return ScoreResult(ok, 1.0 if ok else 0.0)


SCORERS: dict[str, Callable[[Case, Any, dict[str, Any]], ScoreResult]] = {
    "exact_match": score_exact_match,
    "contains": score_contains,
    "regex_match": score_regex_match,
    "numeric_threshold": score_numeric_threshold,
    "recall_at_k": score_recall_at_k,
    "classification": score_classification,
    # "llm_judge" é registrado em judge.py (precisa do adapter)
}


def get_scorer(name: str) -> Callable[[Case, Any, dict[str, Any]], ScoreResult]:
    if name not in SCORERS:
        raise KeyError(f"scorer desconhecido: {name}")
    return SCORERS[name]


# --- agregação de métrica ---------------------------------------------------

def _macro_f1(cases: list[Case], results: list[ScoreResult]) -> float:
    """Macro-F1 sobre rótulos esperados (classificação)."""
    labels = {str(c.get("expected")).strip().lower() for c in cases}
    f1s = []
    for label in labels:
        tp = fp = fn = 0
        for c, r in zip(cases, results, strict=True):
            exp = str(c.get("expected")).strip().lower()
            pred_correct = r.passed
            predicted_label = exp if pred_correct else "__other__"
            if exp == label and predicted_label == label:
                tp += 1
            elif exp != label and predicted_label == label:
                fp += 1
            elif exp == label and predicted_label != label:
                fn += 1
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if (prec + rec) else 0.0)
    return sum(f1s) / len(f1s) if f1s else 0.0


def aggregate(scorer_name: str, cases: list[Case], results: list[ScoreResult]) -> MetricResult:
    n = len(results)
    n_failed = sum(1 for r in results if not r.passed)
    if scorer_name == "recall_at_k":
        metric = "recall_at_k"
        value = sum(r.score for r in results) / n if n else 0.0
    elif scorer_name == "classification":
        metric = "macro_f1"
        value = _macro_f1(cases, results)
    else:
        metric = "pass_rate"
        value = (n - n_failed) / n if n else 0.0
    return MetricResult(metric=metric, value=round(value, 4), n_cases=n, n_failed_cases=n_failed)
