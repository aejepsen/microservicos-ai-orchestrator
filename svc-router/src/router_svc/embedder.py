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
    """Embedding determinístico por hash — estável entre runs, sem rede."""

    def __init__(self, dim: int = 48) -> None:
        self._dim = dim

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.empty((len(texts), self._dim))
        for i, t in enumerate(texts):
            seed = int(hashlib.sha256(t.encode()).hexdigest()[:8], 16)
            rng = np.random.default_rng(seed)
            out[i] = rng.standard_normal(self._dim)
        return out


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
