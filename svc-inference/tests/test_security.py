from __future__ import annotations

from fastapi.testclient import TestClient

from inference.app import State, create_app
from inference.backends import FakeBackend
from inference.config import Settings


def _open_client(**over) -> TestClient:
    base = dict(internal_key="", backend="fake", rate_limit_per_min=100000)
    base.update(over)
    s = Settings(**base)
    return TestClient(create_app(settings=s, state=State(s, FakeBackend())))


def test_missing_key_401(client) -> None:
    body = {"model": "fake-model", "messages": [{"role": "user", "content": "x"}]}
    assert client.post("/v1/chat/completions", json=body).status_code == 401


def test_wrong_key_401(client) -> None:
    assert client.get("/v1/models", headers={"X-Internal-Key": "errada"}).status_code == 401


def test_fail_closed_no_key() -> None:
    c = _open_client(allow_open_access=False)
    assert c.get("/v1/models").status_code == 401


def test_open_access_opt_in() -> None:
    c = _open_client(allow_open_access=True)
    assert c.get("/v1/models").status_code == 200


def test_health_no_auth(client) -> None:
    assert client.get("/health").status_code == 200


def test_metrics_requires_auth(client) -> None:
    assert client.get("/metrics").status_code == 401


def test_docs_disabled(client) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_rate_limit() -> None:
    s = Settings(internal_key="k", backend="fake", rate_limit_per_min=3)
    c = TestClient(create_app(settings=s, state=State(s, FakeBackend())))
    h = {"X-Internal-Key": "k"}
    codes = [c.get("/v1/models", headers=h).status_code for _ in range(5)]
    assert 429 in codes
