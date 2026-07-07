"""Rotas registradas: nome + exemplares (estilo domínios do AI-Orchestrator)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    name: str
    exemplars: list[str]


REGISTRY: list[Route] = [
    Route("financas", [
        "Qual o saldo da conta a pagar?",
        "Gere o relatório de fluxo de caixa do mês.",
        "Quais contas a receber estão vencidas?",
        "Qual o faturamento total do trimestre?",
        "Registre o pagamento da conta.",
    ]),
    Route("rh", [
        "Qual o saldo de férias do funcionário?",
        "Cadastre um novo funcionário.",
        "Quantos funcionários há no departamento?",
        "Atualize o salário do colaborador.",
        "Registre férias para a matrícula.",
    ]),
    Route("estoque", [
        "Quais produtos estão abaixo do ponto de reposição?",
        "Crie uma reserva de estoque para o SKU.",
        "Qual a quantidade em estoque do produto?",
        "Cadastre um produto na categoria.",
        "Mostre o relatório de reposição sugerida.",
    ]),
    Route("vendas", [
        "Liste os pedidos do vendedor da região.",
        "Qual o desconto máximo para o pedido?",
        "Registre um novo pedido de venda.",
        "Mostre os produtos mais vendidos.",
        "Qual o total de vendas por categoria?",
    ]),
]


def registry() -> list[Route]:
    return list(REGISTRY)
