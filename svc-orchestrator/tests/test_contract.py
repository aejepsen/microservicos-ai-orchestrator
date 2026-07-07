from __future__ import annotations

from pathlib import Path

import yaml

SPEC = Path(__file__).resolve().parents[1] / "api" / "openapi.yaml"


def test_openapi_valid() -> None:
    from openapi_spec_validator import validate

    validate(yaml.safe_load(SPEC.read_text()))


def test_all_paths_exercised(client, auth_headers) -> None:
    doc = yaml.safe_load(SPEC.read_text())
    tid = client.post("/v1/chat", json={"query": "qual o saldo?"},
                      headers=auth_headers).json()["thread_id"]
    checks = {
        ("post", "/v1/chat"): lambda: client.post(
            "/v1/chat", json={"query": "saldo?"}, headers=auth_headers),
        ("post", "/v1/chat/{thread_id}/resume"): lambda: client.post(
            f"/v1/chat/{tid}/resume", json={"approve": True}, headers=auth_headers),
        ("get", "/v1/threads/{thread_id}"): lambda: client.get(
            f"/v1/threads/{tid}", headers=auth_headers),
        ("get", "/health"): lambda: client.get("/health"),
        ("get", "/metrics"): lambda: client.get("/metrics", headers=auth_headers),
    }
    declared = {(m, p) for p, item in doc["paths"].items() for m in item}
    assert declared == set(checks), f"YAML != testes: {declared ^ set(checks)}"
    # rota existe = não-404 (resume sem pausa pendente responde 404 de negócio, exceção documentada)
    for key, call in checks.items():
        code = call().status_code
        if key == ("post", "/v1/chat/{thread_id}/resume"):
            assert code in {200, 404}
        else:
            assert code != 404


def test_chat_response_matches_schema(client, auth_headers) -> None:
    body = client.post("/v1/chat", json={"query": "qual o saldo?"},
                       headers=auth_headers).json()
    assert set(body) == {"thread_id", "decision", "domains", "agents", "final", "pending_write"}
    assert all(set(a) == {"domain", "answer", "context_used"} for a in body["agents"])


def test_chat_422_on_missing_query(client, auth_headers) -> None:
    assert client.post("/v1/chat", json={}, headers=auth_headers).status_code == 422


def test_chat_422_on_empty_query(client, auth_headers) -> None:
    assert client.post("/v1/chat", json={"query": ""}, headers=auth_headers).status_code == 422


def test_health_response_shape(client) -> None:
    body = client.get("/health").json()
    assert set(body) == {"status", "version", "deps"}
    assert set(body["deps"]) == {"guardrails", "router", "rag", "inference"}


def test_metrics_response_shape(client, auth_headers) -> None:
    body = client.get("/metrics", headers=auth_headers).json()
    assert set(body) >= {"chats_total", "blocked_total", "paused_total",
                         "by_domain", "latency_ms_p50", "latency_ms_p95"}
