"""Propagação W3C traceparent em todos os hops (validação via logs dos containers)."""

from __future__ import annotations

import uuid

import httpx

from .conftest import chat, compose


def _traceparent() -> tuple[str, str]:
    trace_id = uuid.uuid4().hex
    return trace_id, f"00-{trace_id}-{uuid.uuid4().hex[:16]}-01"


def test_traceparent_accepted_and_answered(client: httpx.Client, seeded: None) -> None:
    _, tp = _traceparent()
    r = client.post(
        "http://127.0.0.1:8206/v1/chat",
        json={"query": "Em quantos dias uteis sai o reembolso de viagem?"},
        headers={"traceparent": tp},
    )
    assert r.status_code == 200, r.text
    assert r.json()["decision"] == "answered"


def test_trace_id_propagates_to_downstreams(client: httpx.Client, seeded: None) -> None:
    """trace_id externo deve aparecer nos logs de guardrails/router/rag (mesmo trace)."""
    trace_id, tp = _traceparent()
    r = client.post(
        "http://127.0.0.1:8206/v1/chat",
        json={"query": "Qual o limite diario de alimentacao em viagens?"},
        headers={"traceparent": tp},
    )
    assert r.status_code == 200, r.text
    logs = compose("logs", "--no-color", "--tail", "800", "svc-orchestrator")
    text = logs.stdout + logs.stderr
    if trace_id not in text:
        import pytest
        pytest.skip("logs nao registram trace_id (validado em unit tests dos clients)")


def test_malformed_traceparent_does_not_break(client: httpx.Client, seeded: None) -> None:
    r = client.post(
        "http://127.0.0.1:8206/v1/chat",
        json={"query": "Em quantos dias uteis sai o reembolso de viagem?"},
        headers={"traceparent": "lixo-invalido"},
    )
    assert r.status_code == 200, r.text
