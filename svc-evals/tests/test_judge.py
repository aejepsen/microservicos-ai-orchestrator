from __future__ import annotations

import pytest

from evals_svc.judge import FakeJudge, parse_verdict, score_llm_judge


def test_fake_judge_faithful() -> None:
    v = FakeJudge().judge("EVIDENCIA: fato1\nRESPOSTA: contem fato1 aqui")
    assert v["faithful"] is True


def test_fake_judge_unfaithful() -> None:
    v = FakeJudge().judge("EVIDENCIA: fato_x\nRESPOSTA: sem a evidencia")
    assert v["faithful"] is False


def test_fake_judge_deterministic() -> None:
    j = FakeJudge()
    p = "EVIDENCIA: a\nRESPOSTA: tem a"
    assert {j.judge(p)["faithful"] for _ in range(5)} == {True}


def test_parse_clean() -> None:
    assert parse_verdict('{"faithful": true}')["faithful"] is True


def test_parse_dirty() -> None:
    assert parse_verdict('lixo antes {"faithful": false} lixo depois')["faithful"] is False


def test_parse_no_json_raises() -> None:
    with pytest.raises(ValueError, match="nenhum JSON"):
        parse_verdict("sem json aqui")


def test_score_llm_judge_needs_adapter() -> None:
    with pytest.raises(RuntimeError, match="sem adapter"):
        score_llm_judge({"expected": "x"}, "y", {})


def test_score_llm_judge_with_fake() -> None:
    r = score_llm_judge({"evidence": "fato"}, "resposta com fato", {"_judge": FakeJudge()})
    assert r.passed
