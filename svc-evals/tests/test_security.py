from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from evals_svc.app import create_app
from evals_svc.config import Settings


def test_missing_key_401(client) -> None:
    assert client.post("/v1/run", json={"suite": "routing_accuracy"}).status_code == 401


def test_wrong_key_401(client) -> None:
    r = client.get("/v1/results", headers={"X-Internal-Key": "errada"})
    assert r.status_code == 401


def test_fail_closed(tmp_path: Path) -> None:
    s = Settings(internal_key="", allow_open_access=False, results_dir=str(tmp_path))
    c = TestClient(create_app(settings=s))
    assert c.get("/v1/results").status_code == 401


def test_health_no_auth(client) -> None:
    assert client.get("/health").status_code == 200


def test_metrics_requires_auth(client) -> None:
    assert client.get("/metrics").status_code == 401


def test_docs_disabled(client) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_ssrf_blocked_metadata(client, auth_headers) -> None:
    r = client.post(
        "/v1/run",
        json={
            "golden_inline": [{"input": "x"}],
            "scorer": "exact_match",
            "mode": "live",
            "target": {"url": "http://169.254.169.254/latest/meta-data", "input_field": "q", "output_pointer": "out"},
        },
        headers=auth_headers,
    )
    assert r.status_code == 422  # SSRF bloqueado


def test_ssrf_blocked_scheme(client, auth_headers) -> None:
    r = client.post(
        "/v1/run",
        json={
            "golden_inline": [{"input": "x"}],
            "scorer": "exact_match",
            "mode": "live",
            "target": {"url": "file:///etc/passwd", "input_field": "q", "output_pointer": "out"},
        },
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_llm_judge_requires_enabled(client, auth_headers) -> None:
    r = client.post(
        "/v1/run",
        json={"golden_inline": [{"expected": "a", "response": "a"}], "scorer": "llm_judge"},
        headers=auth_headers,
    )
    assert r.status_code == 503


def test_rate_limit(tmp_path: Path) -> None:
    s = Settings(internal_key="k", results_dir=str(tmp_path), rate_limit_per_min=3)
    c = TestClient(create_app(settings=s))
    h = {"X-Internal-Key": "k"}
    codes = [c.get("/v1/results", headers=h).status_code for _ in range(5)]
    assert 429 in codes
