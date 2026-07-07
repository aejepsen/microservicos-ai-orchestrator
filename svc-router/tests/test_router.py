from __future__ import annotations

import pytest

from router_svc.embedder import FakeEmbedder
from router_svc.llm import FakeLLM
from router_svc.router import LLMUnavailable, Router

ROUTES = [("financas", ["saldo conta pagar", "fluxo caixa"]),
          ("vendas", ["pedido vendedor", "desconto pedido"])]


def _router(threshold: float, hybrid: bool = True) -> Router:
    return Router(ROUTES, FakeEmbedder(), threshold=threshold, tie_margin=0.05, rrf_k=60, hybrid=hybrid)


def test_semantic_layer_when_above_threshold() -> None:
    plan = _router(-1.0).route("saldo conta pagar", allow_llm=False, llm=None, soft_fallback=True)
    assert plan.layer == "semantic"
    assert len(plan.domains) >= 1


def test_lexical_layer_when_guard_fires_and_semantic_fails() -> None:
    plan = _router(1.1).route("Qual a comissão do vendedor?", allow_llm=False, llm=None, soft_fallback=True)
    assert plan.layer == "lexical"
    assert plan.domains == ["financas", "vendas"]


def test_guards_augment_semantic() -> None:
    # semântica decide + guard adiciona domínios
    plan = _router(-1.0).route("comissão do saldo conta pagar", allow_llm=False, llm=None, soft_fallback=True)
    assert plan.layer == "semantic"
    assert "financas" in plan.domains and "vendas" in plan.domains


def test_llm_layer_when_no_semantic_no_guard() -> None:
    plan = _router(1.1).route("xyz abc def", allow_llm=True, llm=FakeLLM(returns=["vendas"]))
    assert plan.layer == "llm"
    assert plan.domains == ["vendas"]
    assert plan.llm_used is True


def test_llm_unavailable_raises_without_soft() -> None:
    with pytest.raises(LLMUnavailable):
        _router(1.1).route("xyz abc", allow_llm=True, llm=None, soft_fallback=False)


def test_soft_fallback_layer() -> None:
    plan = _router(1.1).route("xyz abc", allow_llm=True, llm=None, soft_fallback=True)
    assert plan.layer == "fallback"
    assert len(plan.domains) == 1


def test_scores_present() -> None:
    plan = _router(-1.0).route("saldo conta pagar", allow_llm=False, llm=None, soft_fallback=True)
    assert set(plan.scores) == {"financas", "vendas"}


def test_no_hybrid_uses_dense() -> None:
    plan = _router(-1.0, hybrid=False).route("pedido vendedor", allow_llm=False, llm=None, soft_fallback=True)
    assert plan.layer == "semantic"
