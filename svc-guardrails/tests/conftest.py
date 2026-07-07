"""Fixtures compartilhadas — embedder fake para não exigir SBERT nos testes de API."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from guardrails.app import State, create_app  # noqa: E402
from guardrails.config import Settings  # noqa: E402


class FakeEmbedder:
    """Embedding determinístico por hash — sem rede, estável entre runs."""

    def __init__(self, dim: int = 32) -> None:
        self._dim = dim

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.empty((len(texts), self._dim))
        for i, t in enumerate(texts):
            seed = int(hashlib.sha256(t.encode()).hexdigest()[:8], 16)
            rng = np.random.default_rng(seed)
            out[i] = rng.standard_normal(self._dim)
        return out


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(internal_key="test-key", models_dir=str(tmp_path), rate_limit_per_min=1000)


@pytest.fixture
def state(settings: Settings) -> State:
    st = State.__new__(State)
    st.settings = settings
    import threading

    from guardrails.ood import OodGuard
    from guardrails.security import RateLimiter

    st.rate_limiter = RateLimiter(settings.rate_limit_per_min)
    st.ood_guard = OodGuard(settings.models_dir)
    st.fit_lock = threading.Lock()
    st.embedder = FakeEmbedder()
    st.analyses_total = st.blocks_total = st.flags_total = 0
    from collections import deque

    st.latencies = deque(maxlen=1000)
    return st


@pytest.fixture
def client(settings: Settings, state: State):
    from fastapi.testclient import TestClient

    return TestClient(create_app(settings=settings, state=state))


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-Internal-Key": "test-key"}
