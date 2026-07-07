from __future__ import annotations

from evals_svc.scorers import (
    aggregate,
    score_classification,
    score_contains,
    score_exact_match,
    score_numeric_threshold,
    score_recall_at_k,
    score_regex_match,
)


def test_exact_match() -> None:
    assert score_exact_match({"expected": "a"}, "a", {}).passed
    assert not score_exact_match({"expected": "a"}, "b", {}).passed


def test_contains_trap() -> None:
    # armadilha: palavra ausente -> negativo
    assert not score_contains({"expected": "xyz"}, "abc def", {}).passed


def test_regex() -> None:
    assert score_regex_match({"expected": r"\d{3}"}, "sku 123", {}).passed


def test_numeric_tolerance() -> None:
    assert score_numeric_threshold({"expected": 10.0}, 10.4, {"tolerance": 0.5}).passed
    assert not score_numeric_threshold({"expected": 10.0}, 11.0, {"tolerance": 0.5}).passed


def test_recall_at_k_out_of_window() -> None:
    assert score_recall_at_k({"expected": "x"}, ["a", "x"], {"k": 3}).passed
    assert not score_recall_at_k({"expected": "x"}, ["a", "b", "c", "x"], {"k": 3}).passed


def test_recall_aggregate() -> None:
    cases = [{"expected": "x"}, {"expected": "y"}]
    results = [score_recall_at_k(cases[0], ["x"], {"k": 3}), score_recall_at_k(cases[1], ["a"], {"k": 3})]
    m = aggregate("recall_at_k", cases, results)
    assert m.value == 0.5 and m.metric == "recall_at_k"


def test_classification_f1_perfect() -> None:
    cases = [{"expected": "rh"}, {"expected": "fin"}]
    results = [score_classification(cases[0], "rh", {}), score_classification(cases[1], "fin", {})]
    m = aggregate("classification", cases, results)
    assert m.value == 1.0 and m.metric == "macro_f1"
