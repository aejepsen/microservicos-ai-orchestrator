from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rag_svc.app import State, create_app
from rag_svc.config import Settings
from rag_svc.embedder import FakeEmbedder
from rag_svc.security import validate_outbound_url
from rag_svc.store import InMemoryStore


def _client(tmp_path: Path, **over) -> TestClient:
    base = dict(internal_key="", vector_store="memory", rate_limit_per_min=100000, models_dir=str(tmp_path))
    base.update(over)
    s = Settings(**base)
    return TestClient(create_app(settings=s, state=State(s, FakeEmbedder(), InMemoryStore())))


def test_missing_key_401(client) -> None:
    assert client.post("/v1/search", json={"query": "x"}).status_code == 401


def test_wrong_key_401(client) -> None:
    assert client.get("/v1/collections", headers={"X-Internal-Key": "x"}).status_code == 401


def test_fail_closed(tmp_path: Path) -> None:
    assert _client(tmp_path, allow_open_access=False).get("/v1/collections").status_code == 401


def test_open_access_opt_in(tmp_path: Path) -> None:
    assert _client(tmp_path, allow_open_access=True).get("/v1/collections").status_code == 200


def test_health_no_auth(client) -> None:
    assert client.get("/health").status_code == 200


def test_metrics_requires_auth(client) -> None:
    assert client.get("/metrics").status_code == 401


def test_docs_disabled(client) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_rate_limit(tmp_path: Path) -> None:
    s = Settings(internal_key="k", vector_store="memory", rate_limit_per_min=3, models_dir=str(tmp_path))
    c = TestClient(create_app(settings=s, state=State(s, FakeEmbedder(), InMemoryStore())))
    h = {"X-Internal-Key": "k"}
    codes = [c.get("/v1/collections", headers=h).status_code for _ in range(5)]
    assert 429 in codes


def test_ssrf_metadata_blocked() -> None:
    with pytest.raises(ValueError, match="SSRF"):
        validate_outbound_url("http://169.254.169.254/", allow_local=False)


def test_ssrf_scheme_blocked() -> None:
    with pytest.raises(ValueError, match="esquema"):
        validate_outbound_url("ftp://host/x", allow_local=False)


def test_ssrf_public_ok() -> None:
    # IP público literal (sem DNS): não é privado/metadata → passa
    validate_outbound_url("https://8.8.8.8:6333", allow_local=False)
