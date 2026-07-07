from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evals_svc.app import create_app  # noqa: E402
from evals_svc.config import Settings  # noqa: E402


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        internal_key="test-key",
        results_dir=str(tmp_path / "results"),
        rate_limit_per_min=100000,
    )


@pytest.fixture
def client(settings: Settings):
    from fastapi.testclient import TestClient

    return TestClient(create_app(settings=settings))


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-Internal-Key": "test-key"}
