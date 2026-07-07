"""Guards léxicos determinísticos: regras que ADICIONAM domínios ao RoutePlan.

Cada guard dispara só com contexto (não palavra solta). Ancoragem evita
falso-positivo em uso legítimo da palavra-gatilho (ex.: "ignore os pedidos
cancelados" não é guard de nada; "custo do produto" é produto, não finanças).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Guard:
    id: str
    description: str
    pattern: re.Pattern[str]
    domains: tuple[str, ...]


_GUARDS: list[Guard] = [
    Guard(
        "comissao_vendas_financas",
        "Comissão envolve vendas (quem vende) e finanças (quanto paga)",
        re.compile(r"\bcomiss[aã]o(?:es)?\b", re.IGNORECASE),
        ("vendas", "financas"),
    ),
    Guard(
        "aprovacao_financas_rh",
        "Quem aprova despesa/férias cruza finanças e RH",
        re.compile(
            r"\bquem\s+aprova\b"
            r"|\baprova[çc][aã]o\s+de\s+(?:despesa|f[ée]rias|adiantamento)\b",
            re.IGNORECASE,
        ),
        ("financas", "rh"),
    ),
    Guard(
        "compra_estoque_vendas",
        "Pedido de compra cruza estoque (baixa) e vendas (pedido)",
        re.compile(r"\b(?:pedido\s+de\s+compra|comprou|ordem\s+de\s+compra)\b", re.IGNORECASE),
        ("estoque", "vendas"),
    ),
    Guard(
        "custo_financas",
        "Custo (exceto 'custo do produto', que é estoque) é finanças",
        re.compile(r"\bcusto\b(?!\s+d[eo]\s+produto)", re.IGNORECASE),
        ("financas",),
    ),
]


def guards() -> list[Guard]:
    return list(_GUARDS)


def apply_guards(query: str) -> tuple[set[str], list[str]]:
    """Retorna (domínios adicionados, ids dos guards que dispararam)."""
    added: set[str] = set()
    fired: list[str] = []
    for g in _GUARDS:
        if g.pattern.search(query):
            added.update(g.domains)
            fired.append(g.id)
    return added, fired
