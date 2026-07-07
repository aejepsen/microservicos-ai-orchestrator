"""Detecção determinística de write intent (HITL) — léxico PT (padrão AIO write_intent.py).

Escrita = verbo imperativo de operação de escrita + objeto. Frases NOMINAIS
("contas a pagar", "relatório de contas a pagar") NÃO são escrita — são leitura.
Leitura nunca pausa.
"""

from __future__ import annotations

import re

# Verbos de escrita (imperativo/infinitivo) das operações dos serviços.
_WRITE_VERBS = (
    r"cadastr\w+|registr\w+|atualiz\w+|alter\w+|delet\w+|remov\w+|exclu\w+|"
    r"crie|criar|adicion\w+|insir\w+|inserir|pag(?:ue|ar)|receb\w+|"
    r"promov\w+|reajust\w+|conced\w+|lanc\w+|edit\w+|salv\w+|aprov\w+"
)

_WRITE_RE = re.compile(rf"\b(?:{_WRITE_VERBS})\b", re.IGNORECASE)

# Frases nominais que contêm "pagar/receber" mas são substantivos (leitura). Armadilha.
_NOMINAL_RE = re.compile(
    r"\bcontas?\s+a\s+(?:pagar|receber)\b|\bvalores?\s+a\s+(?:pagar|receber)\b",
    re.IGNORECASE,
)

# Verbos de leitura explícitos — se a frase é claramente consulta, não é escrita.
_READ_RE = re.compile(
    r"\b(?:qual|quais|quanto|quantos|mostre|liste|exiba|consulte|veja|ver|"
    r"relat[oó]rio|status|saldo|total)\b",
    re.IGNORECASE,
)


def is_write_intent(query: str) -> bool:
    """True se a query é uma operação de escrita que deve pausar no HITL."""
    # Remove frases nominais-armadilha antes de procurar verbo de escrita.
    cleaned = _NOMINAL_RE.sub(" ", query)
    if not _WRITE_RE.search(cleaned):
        return False
    # Tem verbo de escrita. Se também é claramente leitura ("qual...") e o verbo
    # de escrita veio só da parte nominal removida, já teria falhado acima.
    # Verbo de escrita presente + não é pergunta de consulta pura → escrita.
    if _READ_RE.search(cleaned) and not _WRITE_RE.search(cleaned):
        return False
    return True
