"""Resiliência: downstream fora do ar, circuit breaker OPEN e recuperação.

Destrutivo (para/inicia containers) — roda apenas com E2E_RESILIENCE=1.
"""

from __future__ import annotations

import os
import time

import httpx
import pytest

from .conftest import ORCH, chat, compose, wait_healthy

pytestmark = pytest.mark.skipif(
    os.environ.get("E2E_RESILIENCE", "0") != "1",
    reason="destrutivo — exporte E2E_RESILIENCE=1 para rodar",
)


def _deps() -> dict[str, str]:
    return httpx.get(f"{ORCH}/health", timeout=5).json()["deps"]


def test_downstream_down_opens_circuit_and_recovers(
    client: httpx.Client, seeded: None
) -> None:
    assert compose("stop", "svc-inference").returncode == 0
    try:
        # Falhas consecutivas até abrir o circuito (CIRCUIT_FAIL_THRESHOLD=3).
        opened = False
        for _ in range(6):
            r = chat(client, "Em quantos dias uteis sai o reembolso de viagem?")
            assert r.status_code in {200, 503}, r.text
            if _deps().get("inference") == "open":
                opened = True
                break
        assert opened, f"circuito nao abriu: deps={_deps()}"
        assert httpx.get(f"{ORCH}/health", timeout=5).json()["status"] == "degraded"
    finally:
        assert compose("start", "svc-inference").returncode == 0

    # Recuperação: HALF_OPEN -> sucesso -> CLOSED.
    assert wait_healthy("http://127.0.0.1:8206", 120)
    deadline = time.monotonic() + 120
    recovered = False
    while time.monotonic() < deadline:
        time.sleep(5)
        r = chat(client, "Qual o limite diario de alimentacao?")
        if r.status_code == 200 and r.json()["decision"] == "answered":
            if _deps().get("inference") == "closed":
                recovered = True
                break
    assert recovered, f"circuito nao fechou apos recovery: deps={_deps()}"


def test_no_false_circuit_open_on_healthy_stack(client: httpx.Client, seeded: None) -> None:
    """Nenhum circuito deve abrir sem razão com a stack saudável."""
    for _ in range(3):
        r = chat(client, "Em quantos dias uteis sai o reembolso de viagem?")
        assert r.status_code == 200, r.text
    assert all(v == "closed" for v in _deps().values()), _deps()
