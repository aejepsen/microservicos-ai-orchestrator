from __future__ import annotations

import json

from fastapi.testclient import TestClient

from inference.app import State, create_app
from inference.backends import FakeBackend
from inference.config import Settings


def test_chat_completion_envelope(client, auth_headers) -> None:
    r = client.post(
        "/v1/chat/completions",
        json={"model": "fake-model", "messages": [{"role": "user", "content": "oi"}]},
        headers=auth_headers,
    )
    assert r.status_code == 200
    b = r.json()
    assert b["object"] == "chat.completion"
    assert b["choices"][0]["message"]["role"] == "assistant"
    assert b["choices"][0]["finish_reason"] == "stop"
    assert set(b["usage"]) == {"prompt_tokens", "completion_tokens", "total_tokens"}


def test_chat_missing_model(client, auth_headers) -> None:
    r = client.post("/v1/chat/completions", json={"model": "", "messages": [{"role": "user", "content": "x"}]}, headers=auth_headers)
    assert r.status_code == 422


def test_stream_shape_and_done(client, auth_headers) -> None:
    with client.stream(
        "POST", "/v1/chat/completions",
        json={"model": "fake-model", "stream": True, "messages": [{"role": "user", "content": "oi"}]},
        headers=auth_headers,
    ) as s:
        payloads = [ln[6:] for ln in s.iter_lines() if ln.startswith("data: ")]
    assert payloads[-1] == "[DONE]"
    chunks = [json.loads(p) for p in payloads if p != "[DONE]"]
    assert all(c["object"] == "chat.completion.chunk" for c in chunks)
    assert "usage" in chunks[-1]


def test_list_models(client, auth_headers) -> None:
    r = client.get("/v1/models", headers=auth_headers)
    assert r.status_code == 200
    b = r.json()
    assert b["object"] == "list"
    assert b["data"][0]["id"] == "fake-model"


def test_health_ok(client) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["deps"]["circuit"] == "closed"


def test_metrics_accumulate(client, auth_headers) -> None:
    client.post("/v1/chat/completions", json={"model": "fake-model", "messages": [{"role": "user", "content": "um dois"}]}, headers=auth_headers)
    m = client.get("/metrics", headers=auth_headers).json()
    assert m["requests_total"] == 1
    assert m["tokens_input_total"] == 2
    assert m["source"] == "live"


def test_backend_down_returns_503() -> None:
    s = Settings(internal_key="k", backend="fake", rate_limit_per_min=100000)
    st = State(s, FakeBackend(fail_transport=True))
    c = TestClient(create_app(settings=s, state=st))
    r = c.post("/v1/chat/completions", json={"model": "fake-model", "messages": [{"role": "user", "content": "x"}]}, headers={"X-Internal-Key": "k"})
    assert r.status_code == 503


def test_circuit_opens_health_degraded() -> None:
    s = Settings(internal_key="k", backend="fake", rate_limit_per_min=100000, circuit_fail_threshold=2)
    st = State(s, FakeBackend(fail_transport=True))
    c = TestClient(create_app(settings=s, state=st))
    h = {"X-Internal-Key": "k"}
    body = {"model": "fake-model", "messages": [{"role": "user", "content": "x"}]}
    for _ in range(2):
        c.post("/v1/chat/completions", json=body, headers=h)
    assert c.get("/health").json()["status"] == "degraded"
