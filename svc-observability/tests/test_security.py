from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from obs_svc.app import State, create_app
from obs_svc.config import Settings
from obs_svc.scraper import FakeScraper
from obs_svc.security import validate_outbound_url


def _client(**over) -> TestClient:
    base = dict(internal_key="", allow_local_upstream=True, rate_limit_per_min=100000)
    base.update(over)
    s = Settings(**base)
    return TestClient(create_app(settings=s, state=State(s, FakeScraper({}))))


def test_missing_key_401(client) -> None:
    assert client.get("/v1/overview").status_code == 401


def test_wrong_key_401(client) -> None:
    assert client.get("/v1/services", headers={"X-Internal-Key": "x"}).status_code == 401


def test_fail_closed() -> None:
    assert _client(allow_open_access=False).get("/v1/overview").status_code == 401


def test_open_access_opt_in() -> None:
    assert _client(allow_open_access=True).get("/v1/overview").status_code == 200


def test_health_no_auth(client) -> None:
    assert client.get("/health").status_code == 200


def test_metrics_requires_auth(client) -> None:
    assert client.get("/metrics").status_code == 401


def test_docs_disabled(client) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_rate_limit() -> None:
    s = Settings(internal_key="k", allow_local_upstream=True, rate_limit_per_min=3)
    c = TestClient(create_app(settings=s, state=State(s, FakeScraper({}))))
    h = {"X-Internal-Key": "k"}
    codes = [c.get("/v1/services", headers=h).status_code for _ in range(5)]
    assert 429 in codes


def test_ssrf_metadata_blocked() -> None:
    with pytest.raises(ValueError, match="SSRF"):
        validate_outbound_url("http://169.254.169.254/", allow_local=False)


def test_ssrf_scheme_blocked() -> None:
    with pytest.raises(ValueError, match="esquema"):
        validate_outbound_url("gopher://x/", allow_local=False)


def test_ssrf_public_ip_ok() -> None:
    # IP público literal (sem DNS) passa — template §8.5
    validate_outbound_url("http://8.8.8.8:9090/metrics", allow_local=False)
