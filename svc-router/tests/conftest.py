from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.getLogger("httpx").setLevel(logging.WARNING)

from router_svc.app import State, create_app  # noqa: E402
from router_svc.config import Settings  # noqa: E402
from router_svc.embedder import FakeEmbedder  # noqa: E402


@pytest.fixture
def settings() -> Settings:
    return Settings(internal_key="test-key", rate_limit_per_min=100000, llm_fallback_soft=True)


@pytest.fixture
def client(settings: Settings):
    from fastapi.testclient import TestClient

    # embedder fake (offline); llm None (soft-fallback ligado)
    return TestClient(create_app(settings=settings, state=State(settings, FakeEmbedder(), None)))


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-Internal-Key": "test-key"}
