from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tests.conftest import build_orch

from orch_svc.app import State, create_app
from orch_svc.circuit import DownstreamError
from orch_svc.config import Settings
from orch_svc.security import client_ip, validate_outbound_url


def _client(**over) -> TestClient:
    base = dict(internal_key="", allow_local_downstream=True, rate_limit_per_min=100000)
    base.update(over)
    s = Settings(**base)
    return TestClient(create_app(settings=s, state=State(s, build_orch())))


def test_missing_key_401(client) -> None:
    assert client.post("/v1/chat", json={"query": "x"}).status_code == 401


def test_wrong_key_401(client) -> None:
    r = client.post("/v1/chat", json={"query": "x"}, headers={"X-Internal-Key": "errada"})
    assert r.status_code == 401


def test_fail_closed_sem_key() -> None:
    assert _client(allow_open_access=False).post(
        "/v1/chat", json={"query": "x"}).status_code == 401


def test_open_access_opt_in() -> None:
    assert _client(allow_open_access=True).post(
        "/v1/chat", json={"query": "saldo?"}).status_code == 200


def test_health_no_auth(client) -> None:
    assert client.get("/health").status_code == 200


def test_metrics_requires_auth(client) -> None:
    assert client.get("/metrics").status_code == 401


def test_docs_disabled(client) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_rate_limit() -> None:
    c = _client(internal_key="k", rate_limit_per_min=3)
    h = {"X-Internal-Key": "k"}
    codes = [c.post("/v1/chat", json={"query": "saldo?"}, headers=h).status_code
             for _ in range(5)]
    assert 429 in codes


def test_ssrf_metadata_blocked() -> None:
    with pytest.raises(ValueError, match="SSRF"):
        validate_outbound_url("http://169.254.169.254/", allow_local=False)


def test_ssrf_scheme_blocked() -> None:
    with pytest.raises(ValueError, match="esquema"):
        validate_outbound_url("ftp://host/x", allow_local=False)


def test_ssrf_public_ok() -> None:
    # IP público literal (sem DNS): não é privado/metadata → passa
    validate_outbound_url("https://8.8.8.8:8202", allow_local=False)


def test_ssrf_local_opt_in() -> None:
    validate_outbound_url("http://127.0.0.1:8200", allow_local=True)


def test_client_ip_headers() -> None:
    class _Req:
        def __init__(self, headers: dict[str, str]) -> None:
            self.headers = headers
            self.client = None

    assert client_ip(_Req({"cf-connecting-ip": "1.2.3.4"})) == "1.2.3.4"  # type: ignore[arg-type]
    assert client_ip(_Req({"x-forwarded-for": "5.6.7.8, 9.9.9.9"})) == "5.6.7.8"  # type: ignore[arg-type]
    assert client_ip(_Req({})) == "unknown"  # type: ignore[arg-type]


def test_guardrails_failclosed(auth_headers) -> None:
    class DownGuardrails:
        def analyze(self, text: str, trace: str):
            raise DownstreamError("fake: guardrails fora")

    s = Settings(internal_key="test-key", allow_local_downstream=True,
                 rate_limit_per_min=100000)
    orch = build_orch()
    orch._g = DownGuardrails()
    c = TestClient(create_app(settings=s, state=State(s, orch)))
    r = c.post("/v1/chat", json={"query": "qual o saldo?"}, headers=auth_headers)
    assert r.status_code == 503


def test_traceparent_propagado_aos_downstream(auth_headers) -> None:
    orch = build_orch(domains=["financas", "rh"])
    s = Settings(internal_key="test-key", allow_local_downstream=True,
                 rate_limit_per_min=100000)
    c = TestClient(create_app(settings=s, state=State(s, orch)))
    trace = "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"
    r = c.post("/v1/chat", json={"query": "saldo e ferias?"},
               headers={**auth_headers, "traceparent": trace})
    assert r.status_code == 200
    for fake in (orch._g, orch._r, orch._rag, orch._inf):
        assert fake.calls and all(t == trace for t in fake.calls)


def test_traceparent_gerado_quando_ausente(auth_headers) -> None:
    orch = build_orch()
    s = Settings(internal_key="test-key", allow_local_downstream=True,
                 rate_limit_per_min=100000)
    c = TestClient(create_app(settings=s, state=State(s, orch)))
    r = c.post("/v1/chat", json={"query": "saldo?"}, headers=auth_headers)
    assert r.status_code == 200
    trace = orch._g.calls[0]
    parts = trace.split("-")
    assert len(parts) == 4 and parts[0] == "00" and len(parts[1]) == 32 and len(parts[2]) == 16


def test_erro_interno_sem_stack(auth_headers) -> None:
    orch = build_orch()

    def boom(text: str, trace: str):
        raise RuntimeError("segredo interno")

    orch._g = type("G", (), {"analyze": staticmethod(boom)})()
    s = Settings(internal_key="test-key", allow_local_downstream=True,
                 rate_limit_per_min=100000)
    c = TestClient(create_app(settings=s, state=State(s, orch)),
                   raise_server_exceptions=False)
    r = c.post("/v1/chat", json={"query": "saldo?"}, headers=auth_headers)
    assert r.status_code == 500
    assert "segredo" not in r.text and "RuntimeError" not in r.text
