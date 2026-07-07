from __future__ import annotations

import pytest

from evals_svc.runner import run_suite


def test_offline_pass_rate() -> None:
    cases = [{"expected": "a", "response": "a"}, {"expected": "b", "response": "b"}]
    out = run_suite(cases, "exact_match", {}, {"comparator": ">=", "threshold": 1.0})
    assert out.value == 1.0 and out.passed is True and out.n_failed_cases == 0


def test_offline_gate_fail() -> None:
    cases = [{"expected": "a", "response": "a"}, {"expected": "b", "response": "z"}]
    out = run_suite(cases, "exact_match", {}, {"comparator": ">=", "threshold": 0.9})
    assert out.value == 0.5 and out.passed is False


def test_no_gate_returns_none() -> None:
    out = run_suite([{"expected": "a", "response": "a"}], "exact_match", {}, None)
    assert out.passed is None


def test_empty_golden_raises() -> None:
    with pytest.raises(ValueError, match="vazio"):
        run_suite([], "exact_match", {}, None)


def test_offline_requires_response() -> None:
    with pytest.raises(ValueError, match="response"):
        run_suite([{"expected": "a"}], "exact_match", {}, None)


def test_per_case_marks_trap() -> None:
    out = run_suite([{"expected": "a", "response": "a", "trap": True}], "exact_match", {}, None)
    assert out.per_case[0]["trap"] is True
