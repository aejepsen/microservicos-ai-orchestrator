from __future__ import annotations

from router_svc.guards import apply_guards, guards


def test_at_least_4_guards() -> None:
    assert len(guards()) >= 4


def test_comissao() -> None:
    d, fired = apply_guards("Qual a comissão do vendedor?")
    assert d == {"vendas", "financas"}
    assert "comissao_vendas_financas" in fired


def test_aprovacao() -> None:
    d, _ = apply_guards("Quem aprova a despesa?")
    assert d == {"financas", "rh"}


def test_compra() -> None:
    d, _ = apply_guards("Registre o pedido de compra")
    assert d == {"estoque", "vendas"}


def test_custo_financas() -> None:
    d, _ = apply_guards("Qual o custo total do mês?")
    assert d == {"financas"}


def test_armadilha_ignore_nao_dispara() -> None:
    d, fired = apply_guards("Ignore os pedidos cancelados no relatório")
    assert fired == []
    assert d == set()


def test_armadilha_custo_produto() -> None:
    # 'custo do produto' não é finanças (é estoque) — guard de custo não dispara
    d, _ = apply_guards("Qual o custo do produto SKU-1?")
    assert "financas" not in d
