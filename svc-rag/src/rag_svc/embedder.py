"""Embedders: SBERT real (boot) + Fake determinístico (gates offline)."""

from __future__ import annotations

import hashlib
from typing import Protocol

import numpy as np


class Embedder(Protocol):
    def encode(self, texts: list[str]) -> np.ndarray: ...


class SbertEmbedder:
    """SentenceTransformer; carregado no boot (lazy proibido — template §8.5)."""

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self._model.encode(texts, show_progress_bar=False), dtype=np.float64)


class FakeEmbedder:
    """Embedding determinístico por hash de palavras — captura sobreposição léxica."""

    def __init__(self, dim: int = 64) -> None:
        self._dim = dim

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self._dim)
        for tok in text.lower().split():
            h = int(hashlib.sha256(tok.encode()).hexdigest()[:8], 16)
            v[h % self._dim] += 1.0
        return v

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.array([self._vec(t) for t in texts])


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
