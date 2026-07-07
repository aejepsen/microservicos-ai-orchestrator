from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.getLogger("httpx").setLevel(logging.WARNING)

from rag_svc.app import State, create_app  # noqa: E402
from rag_svc.config import Settings  # noqa: E402
from rag_svc.embedder import FakeEmbedder  # noqa: E402
from rag_svc.store import InMemoryStore  # noqa: E402


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        internal_key="test-key", vector_store="memory",
        rate_limit_per_min=100000, models_dir=str(tmp_path),
    )


@pytest.fixture
def client(settings: Settings):
    from fastapi.testclient import TestClient

    return TestClient(create_app(settings=settings, state=State(settings, FakeEmbedder(), InMemoryStore())))


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-Internal-Key": "test-key"}
