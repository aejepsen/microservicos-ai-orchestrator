"""Matriz de integração: todos os upstreams raspáveis e dependências saudáveis."""

from __future__ import annotations

import httpx

from .conftest import OBS, ORCH, RAG

EXPECTED_UPSTREAMS = {
    "svc-guardrails",
    "svc-evals",
    "svc-inference",
    "svc-router",
    "svc-rag",
    "svc-orchestrator",
}


def test_observability_scrapes_all_upstreams(client: httpx.Client) -> None:
    r = client.post(f"{OBS}/v1/refresh")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["failed"] == 0, f"upstreams com falha de scrape: {body}"
    assert body["ok"] == body["scraped"] >= 5


def test_orchestrator_deps_all_closed(client: httpx.Client) -> None:
    deps = httpx.get(f"{ORCH}/health", timeout=5).json()["deps"]
    assert set(deps) == {"guardrails", "router", "rag", "inference"}
    assert all(v == "closed" for v in deps.values()), deps


def test_exposed_services_health_matrix(client: httpx.Client) -> None:
    for url in (ORCH, RAG, OBS):
        r = httpx.get(f"{url}/health", timeout=5)
        assert r.status_code == 200, f"{url}: {r.status_code}"
        assert r.json()["status"] in {"ok", "degraded"}


def test_all_services_reject_missing_key(client: httpx.Client) -> None:
    """Fail-closed transversal: endpoints protegidos exigem X-Internal-Key."""
    cases = [
        ("POST", f"{ORCH}/v1/chat", {"query": "oi"}),
        ("POST", f"{RAG}/v1/ingest", {"collection": "x", "documents": []}),
        ("POST", f"{OBS}/v1/refresh", None),
    ]
    for method, url, body in cases:
        r = httpx.request(method, url, json=body, timeout=10)
        assert r.status_code == 401, f"{url}: esperava 401, veio {r.status_code}"
