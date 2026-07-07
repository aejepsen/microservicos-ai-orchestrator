from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("orch").setLevel(logging.ERROR)

from orch_svc.app import State, create_app  # noqa: E402
from orch_svc.clients import FakeGuardrails, FakeInference, FakeRag, FakeRouter  # noqa: E402
from orch_svc.config import Settings  # noqa: E402
from orch_svc.orchestrator import Breakers, Orchestrator  # noqa: E402


def build_orch(guard="allow", domains=None, rag=True, inf_fail=False, hitl=False):
    return Orchestrator(
        FakeGuardrails(guard), FakeRouter(domains or ["financas"]),
        FakeRag() if rag else None, FakeInference(fail_transport=inf_fail),
        Breakers(3, 30), hitl_enabled=hitl,
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(internal_key="test-key", allow_local_downstream=True, rate_limit_per_min=100000)


@pytest.fixture
def client(settings: Settings):
    from fastapi.testclient import TestClient

    return TestClient(create_app(settings=settings, state=State(settings, build_orch())))


@pytest.fixture
def hitl_client(settings: Settings):
    from fastapi.testclient import TestClient

    return TestClient(create_app(settings=settings, state=State(settings, build_orch(hitl=True))))


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-Internal-Key": "test-key"}
