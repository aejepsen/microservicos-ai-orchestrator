"""Smoke opcional contra o ecossistema real (docker compose com os 4 downstream no ar).

Roda apenas com SMOKE_BASE_URL definido (ex.: http://127.0.0.1:8206) e
SMOKE_INTERNAL_KEY. Sem env → skip (nenhum gate depende de serviço no ar).
"""

from __future__ import annotations

import os

import pytest

BASE = os.environ.get("SMOKE_BASE_URL", "")
KEY = os.environ.get("SMOKE_INTERNAL_KEY", "")

pytestmark = pytest.mark.skipif(
    not BASE, reason="SMOKE_BASE_URL nao definido (smoke exige ecossistema no ar)"
)


def _headers() -> dict[str, str]:
    return {"X-Internal-Key": KEY} if KEY else {}


def test_health_ok() -> None:
    import httpx

    r = httpx.get(f"{BASE}/health", timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] in {"ok", "degraded"}


def test_chat_multidominio_eventos() -> None:
    import httpx

    query = "qual o saldo em caixa e quantos funcionarios de ferias?"
    with httpx.stream(
        "POST", f"{BASE}/v1/chat", json={"query": query, "stream": True},
        headers=_headers(), timeout=120,
    ) as r:
        assert r.status_code == 200
        events = [ln[len("event: "):] for ln in r.iter_lines() if ln.startswith("event: ")]
    assert events[0] == "route"
    assert "agent" in events and "final" in events
    assert events[-1] == "done"


def test_metrics_live() -> None:
    import httpx

    r = httpx.get(f"{BASE}/metrics", headers=_headers(), timeout=10)
    assert r.status_code == 200
    assert r.json()["source"] == "live"
