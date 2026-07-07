from __future__ import annotations

import pytest

from evals_svc.jsonpath import extract


def test_dict_path() -> None:
    assert extract({"a": {"b": {"c": 42}}}, "a.b.c") == 42


def test_list_index() -> None:
    assert extract({"items": [{"v": 1}, {"v": 2}]}, "items.1.v") == 2


def test_root() -> None:
    assert extract({"x": 1}, "$") == {"x": 1}


def test_missing_key_raises() -> None:
    with pytest.raises(KeyError):
        extract({"a": 1}, "b")


def test_no_code_execution() -> None:
    # ponteiro nunca é interpretado como código; chave literal inexistente falha
    with pytest.raises((KeyError, ValueError)):
        extract({"a": 1}, "__import__")
