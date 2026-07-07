"""Extrator de ponteiro seguro (subset de JSONPath) — SEM eval/exec.

Suporta: chaves de dict (`a.b.c`) e índices de lista (`a.0.b` ou `a[0].b`).
Nada além disso. Conteúdo nunca é interpretado como código.
"""

from __future__ import annotations

import re
from typing import Any

_TOKEN_RE = re.compile(r"[^.\[\]]+")


def extract(data: Any, pointer: str) -> Any:
    """Navega `data` pelo ponteiro. Lança KeyError/IndexError se caminho inexistente."""
    if not pointer or pointer == "$":
        return data
    pointer = pointer.lstrip("$.")
    cur = data
    for token in _TOKEN_RE.findall(pointer):
        if isinstance(cur, dict):
            cur = cur[token]
        elif isinstance(cur, (list, tuple)):
            cur = cur[int(token)]
        else:
            raise KeyError(f"ponteiro nao navegavel em '{token}'")
    return cur
