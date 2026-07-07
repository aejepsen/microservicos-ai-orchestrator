from __future__ import annotations

import pytest

from orch_svc.write_intent import is_write_intent


@pytest.mark.parametrize("q", [
    "Cadastre um novo funcionário",
    "Pague a conta 231",
    "Atualize o salário do 210",
    "Delete o produto X",
    "Registre férias para a matrícula 33",
    "Crie uma reserva de estoque",
    "Aprove o adiantamento",
])
def test_write_ops_detected(q: str) -> None:
    assert is_write_intent(q)


@pytest.mark.parametrize("q", [
    "Qual o saldo da conta?",
    "Liste os pedidos do vendedor",
    "Quantos funcionários há no RH?",
    "Mostre o relatório de vendas",
    "Qual o total de comissões?",
])
def test_reads_not_write(q: str) -> None:
    assert not is_write_intent(q)


@pytest.mark.parametrize("q", [
    "Qual o total de contas a pagar?",
    "Gere o relatório de contas a pagar",
    "Liste as contas a receber vencidas",
])
def test_armadilha_nominal(q: str) -> None:
    # frase nominal "contas a pagar/receber" NÃO é escrita
    assert not is_write_intent(q)
