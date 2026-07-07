from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from router_svc.app import State, create_app
from router_svc.config import Settings
from router_svc.embedder import FakeEmbedder
from router_svc.security import validate_outbound_url


def _client(**over) -> TestClient:
    base = dict(internal_key="", rate_limit_per_min=100000, llm_fallback_soft=True)
    base.update(over)
    s = Settings(**base)
    return TestClient(create_app(settings=s, state=State(s, FakeEmbedder(), None)))


def test_missing_key_401(client) -> None:
    assert client.post("/v1/route", json={"query": "oi"}).status_code == 401


def test_wrong_key_401(client) -> None:
    assert client.get("/v1/routes", headers={"X-Internal-Key": "x"}).status_code == 401


def test_fail_closed() -> None:
    assert _client(allow_open_access=False).get("/v1/routes").status_code == 401


def test_open_access_opt_in() -> None:
    assert _client(allow_open_access=True).get("/v1/routes").status_code == 200


def test_health_no_auth(client) -> None:
    assert client.get("/health").status_code == 200


def test_metrics_requires_auth(client) -> None:
    assert client.get("/metrics").status_code == 401


def test_docs_disabled(client) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_rate_limit() -> None:
    s = Settings(internal_key="k", rate_limit_per_min=3, llm_fallback_soft=True)
    c = TestClient(create_app(settings=s, state=State(s, FakeEmbedder(), None)))
    h = {"X-Internal-Key": "k"}
    codes = [c.get("/v1/routes", headers=h).status_code for _ in range(5)]
    assert 429 in codes


def test_ssrf_metadata_blocked() -> None:
    with pytest.raises(ValueError, match="SSRF"):
        validate_outbound_url("http://169.254.169.254/latest", allow_local=False)


def test_ssrf_scheme_blocked() -> None:
    with pytest.raises(ValueError, match="esquema"):
        validate_outbound_url("file:///etc/passwd", allow_local=False)


def test_ssrf_public_ok() -> None:
    validate_outbound_url("https://example.com/v1", allow_local=False)
