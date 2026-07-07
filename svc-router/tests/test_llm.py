from __future__ import annotations

from router_svc.llm import FakeLLM, _parse_domains


def test_fake_llm_returns_configured() -> None:
    assert FakeLLM(returns=["vendas", "rh"]).classify("q", ["vendas", "rh", "financas"]) == ["vendas", "rh"]


def test_fake_llm_intersects_allowed() -> None:
    # 'invalido' não está em allowed -> filtrado
    assert FakeLLM(returns=["vendas", "invalido"]).classify("q", ["vendas"]) == ["vendas"]


def test_fake_llm_default_first_allowed() -> None:
    assert FakeLLM().classify("q", ["financas", "rh"]) == ["financas"]


def test_parse_domains_clean() -> None:
    assert _parse_domains('{"domains": ["rh"]}', ["rh", "vendas"]) == ["rh"]


def test_parse_domains_dirty() -> None:
    assert _parse_domains('lixo {"domains": ["vendas"]} fim', ["vendas"]) == ["vendas"]


def test_parse_domains_filters_disallowed() -> None:
    assert _parse_domains('{"domains": ["x", "rh"]}', ["rh"]) == ["rh"]


def test_parse_domains_no_json() -> None:
    assert _parse_domains("sem json", ["rh"]) == []


def test_parse_domains_bad_json() -> None:
    assert _parse_domains("{quebrado", ["rh"]) == []
