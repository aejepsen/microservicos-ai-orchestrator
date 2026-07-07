"""BM25 Okapi (stdlib) + Reciprocal Rank Fusion (padrão AI-Orchestrator bm25.py).

RRF funde dois rankings por soma de 1/(k+rank), rank começando em 1.
"""

from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25:
    """BM25 Okapi sobre um corpus fixo de documentos (exemplares por rota)."""

    def __init__(self, corpus: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._docs = [tokenize(d) for d in corpus]
        self._doc_len = [len(d) for d in self._docs]
        self._avgdl = sum(self._doc_len) / len(self._docs) if self._docs else 0.0
        self._freqs = [Counter(d) for d in self._docs]
        n = len(self._docs)
        df: Counter[str] = Counter()
        for doc in self._docs:
            for term in set(doc):
                df[term] += 1
        self._idf = {
            term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()
        }

    def scores(self, query: str) -> list[float]:
        q = tokenize(query)
        out = []
        for i, freqs in enumerate(self._freqs):
            score = 0.0
            for term in q:
                if term not in freqs:
                    continue
                idf = self._idf.get(term, 0.0)
                tf = freqs[term]
                norm = 1 - self._b + self._b * self._doc_len[i] / (self._avgdl or 1)
                denom = tf + self._k1 * norm
                score += idf * (tf * (self._k1 + 1)) / (denom or 1)
            out.append(score)
        return out


def rrf_fuse(dense_rank: list[int], lexical_rank: list[int], k: int = 60) -> list[float]:
    """Recebe, para cada doc, sua posição (rank, base 1) em cada ranking. Retorna score RRF."""
    return [
        1.0 / (k + dr) + 1.0 / (k + lr)
        for dr, lr in zip(dense_rank, lexical_rank, strict=True)
    ]


def ranks_from_scores(scores: list[float]) -> list[int]:
    """Converte scores em ranks base-1 (maior score = rank 1). Empates: ordem estável."""
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    ranks = [0] * len(scores)
    for position, idx in enumerate(order, start=1):
        ranks[idx] = position
    return ranks
