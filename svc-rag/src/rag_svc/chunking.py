"""Chunking por seção (headers Markdown) + limite de tamanho com overlap.

Nunca corta no meio de palavra. Não trata linha parecendo header DENTRO de
bloco de código (```) como seção. Preserva ordem e origem.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADER_RE = re.compile(r"^#{1,6}\s+\S")
_FENCE_RE = re.compile(r"^\s*```")


@dataclass(frozen=True)
class Chunk:
    text: str
    section: str
    index: int


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Retorna [(titulo_secao, corpo)]. Ignora headers dentro de code fences."""
    sections: list[tuple[str, list[str]]] = []
    current_title = ""
    current: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            current.append(line)
            continue
        if not in_fence and _HEADER_RE.match(line):
            if current or current_title:
                sections.append((current_title, current))
            current_title = line.lstrip("#").strip()
            current = []
        else:
            current.append(line)
    if current or current_title:
        sections.append((current_title, current))
    return [(t, "\n".join(body).strip()) for t, body in sections]


def _split_by_size(body: str, max_chars: int, overlap: int) -> list[str]:
    """Divide por tamanho sem cortar palavra; overlap por palavras."""
    if len(body) <= max_chars:
        return [body] if body else []
    words = body.split()
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for w in words:
        if cur_len + len(w) + 1 > max_chars and cur:
            chunks.append(" ".join(cur))
            # overlap: mantém as últimas palavras que cabem em `overlap` chars
            back: list[str] = []
            back_len = 0
            for bw in reversed(cur):
                if back_len + len(bw) + 1 > overlap:
                    break
                back.insert(0, bw)
                back_len += len(bw) + 1
            cur = back
            cur_len = back_len
        cur.append(w)
        cur_len += len(w) + 1
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def chunk_document(text: str, max_chars: int = 800, overlap: int = 100) -> list[Chunk]:
    out: list[Chunk] = []
    idx = 0
    for title, body in _split_sections(text):
        if not body:
            continue
        for piece in _split_by_size(body, max_chars, overlap):
            out.append(Chunk(text=piece, section=title, index=idx))
            idx += 1
    return out
