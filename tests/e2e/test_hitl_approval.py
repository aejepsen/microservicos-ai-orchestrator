"""HITL: pausa em write intent, retoma com approve, rejeita, e armadilha nominal."""

from __future__ import annotations

import httpx

from .conftest import ORCH, chat


def _paused_thread(client: httpx.Client, query: str) -> dict:
    r = chat(client, query)  # allow_write=False (default) -> write intent pausa
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision"] == "paused", f"esperava paused, veio {body['decision']}"
    assert body["pending_write"], "pending_write vazio na pausa"
    return body


def test_write_intent_pauses(client: httpx.Client, seeded: None) -> None:
    body = _paused_thread(client, "Cadastre um novo funcionario chamado Joao Silva")
    tid = body["thread_id"]
    st = client.get(f"{ORCH}/v1/threads/{tid}")
    assert st.status_code == 200
    assert st.json()["decision"] == "paused"


def test_resume_reject_never_writes(client: httpx.Client, seeded: None) -> None:
    tid = _paused_thread(client, "Cadastre um novo fornecedor de TI")["thread_id"]
    r = client.post(f"{ORCH}/v1/chat/{tid}/resume", json={"approve": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision"] == "answered"
    assert body["pending_write"] is None
    assert "rejeitada" in (body["final"] or "").lower()


def test_resume_approve_executes(client: httpx.Client, seeded: None) -> None:
    tid = _paused_thread(client, "Registre o pagamento da fatura 123")["thread_id"]
    r = client.post(f"{ORCH}/v1/chat/{tid}/resume", json={"approve": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision"] == "answered"
    assert body["pending_write"] is None
    assert body["final"]


def test_resume_twice_is_404(client: httpx.Client, seeded: None) -> None:
    tid = _paused_thread(client, "Atualize o salario do funcionario 42")["thread_id"]
    assert client.post(f"{ORCH}/v1/chat/{tid}/resume", json={"approve": False}).status_code == 200
    r = client.post(f"{ORCH}/v1/chat/{tid}/resume", json={"approve": True})
    assert r.status_code == 404


def test_nominal_phrase_trap_is_read(client: httpx.Client, seeded: None) -> None:
    """Armadilha: 'contas a pagar' é frase nominal (leitura) — NUNCA pausa."""
    r = chat(client, "Qual o total de contas a pagar deste mes?")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision"] == "answered", "frase nominal pausou indevidamente"
    assert body["pending_write"] is None
