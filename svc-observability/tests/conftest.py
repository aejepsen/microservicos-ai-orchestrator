from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("obs").setLevel(logging.ERROR)

from obs_svc.app import State, create_app  # noqa: E402
from obs_svc.config import Settings  # noqa: E402
from obs_svc.scraper import FakeScraper  # noqa: E402

PAYLOADS = {
    "svc-guardrails": {"source": "live", "analyses_total": 5, "blocks_total": 1},
    "svc-evals": {"source": "live", "runs_total": 3},
    "svc-inference": {"source": "live", "requests_total": 7, "tokens_input_total": 100, "tokens_output_total": 40},
    "svc-router": {"source": "live", "routes_total": 9, "by_layer": {"semantic": 5, "lexical": 4}},
    "svc-rag": {"source": "live", "searches_total": 2},
}


@pytest.fixture
def settings() -> Settings:
    return Settings(internal_key="test-key", allow_local_upstream=True, rate_limit_per_min=100000)


@pytest.fixture
def state(settings: Settings) -> State:
    st = State(settings, FakeScraper(PAYLOADS))
    st.agg.refresh()
    return st


@pytest.fixture
def client(settings: Settings, state: State):
    from fastapi.testclient import TestClient

    return TestClient(create_app(settings=settings, state=state))


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-Internal-Key": "test-key"}
