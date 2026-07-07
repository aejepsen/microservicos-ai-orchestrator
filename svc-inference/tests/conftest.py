from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.getLogger("httpx").setLevel(logging.WARNING)

from inference.app import State, create_app  # noqa: E402
from inference.backends import FakeBackend  # noqa: E402
from inference.config import Settings  # noqa: E402


@pytest.fixture
def settings() -> Settings:
    return Settings(internal_key="test-key", backend="fake", rate_limit_per_min=100000)


@pytest.fixture
def fake_backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def client(settings: Settings, fake_backend: FakeBackend):
    from fastapi.testclient import TestClient

    return TestClient(create_app(settings=settings, state=State(settings, fake_backend)))


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-Internal-Key": "test-key"}
