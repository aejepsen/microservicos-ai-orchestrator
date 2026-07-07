"""Sanitização determinística de entrada.

Remove vetores de contrabando de instrução que não dependem de semântica:
caracteres de controle, zero-width, delimitadores de template de chat.
Nunca altera conteúdo legítimo além de normalizar espaços.
"""

from __future__ import annotations

import re

# Caracteres de controle exceto \n e \t (mantidos: estrutura legítima).
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Zero-width e afins usados para quebrar detectores lexicais.
_ZERO_WIDTH_RE = re.compile(r"[​‌‍⁠﻿]")

# Delimitadores de template de chat que jamais pertencem a input de usuário.
_CHAT_DELIMITERS_RE = re.compile(
    r"<\|im_start\|>|<\|im_end\|>|<\|system\|>|<\|assistant\|>|<\|user\|>"
    r"|\[/?INST\]|<<SYS>>|<</SYS>>",
    re.IGNORECASE,
)

_MULTISPACE_RE = re.compile(r"[ \t]{2,}")


def sanitize(text: str) -> tuple[str, list[str]]:
    """Retorna (texto_sanitizado, ações_aplicadas)."""
    actions: list[str] = []
    out = text
    if _CONTROL_RE.search(out):
        out = _CONTROL_RE.sub("", out)
        actions.append("control_chars_removed")
    if _ZERO_WIDTH_RE.search(out):
        out = _ZERO_WIDTH_RE.sub("", out)
        actions.append("zero_width_removed")
    if _CHAT_DELIMITERS_RE.search(out):
        out = _CHAT_DELIMITERS_RE.sub(" ", out)
        actions.append("chat_delimiters_neutralized")
    collapsed = _MULTISPACE_RE.sub(" ", out)
    if collapsed != out:
        out = collapsed
        actions.append("whitespace_collapsed")
    return out.strip(), actions
