"""Fixtures da suite E2E (FASE 8).

Pré-requisito: stack no ar via `docker compose -f docker-compose.e2e.yml up -d --build`
(ou exporte E2E_AUTOSTART=1 para a suite subir/derrubar o compose sozinha).

Env:
  E2E_KEY         chave interna (default: e2e-local-key)
  E2E_AUTOSTART   1 = sobe o compose na sessão e derruba no fim
  E2E_RESILIENCE  1 = habilita testes destrutivos (stop/start de container)
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Iterator

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ["docker", "compose", "-f", str(ROOT / "docker-compose.e2e.yml")]

KEY = os.environ.get("E2E_KEY", "e2e-local-key")
ORCH = "http://127.0.0.1:8206"
RAG = "http://127.0.0.1:8204"
OBS = "http://127.0.0.1:8205"

CHAT_TIMEOUT = float(os.environ.get("E2E_CHAT_TIMEOUT_S", "180"))


def compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*COMPOSE, *args], capture_output=True, text=True, check=False, cwd=ROOT
    )


def _up(url: str, timeout: float = 3.0) -> bool:
    try:
        return httpx.get(f"{url}/health", timeout=timeout).status_code == 200
    except httpx.HTTPError:
        return False


def wait_healthy(url: str, deadline_s: float = 300.0) -> bool:
    start = time.monotonic()
    while time.monotonic() - start < deadline_s:
        if _up(url):
            return True
        time.sleep(2)
    return False


@pytest.fixture(scope="session")
def stack() -> Iterator[None]:
    autostart = os.environ.get("E2E_AUTOSTART", "0") == "1"
    started_here = False
    if not _up(ORCH):
        if not autostart:
            pytest.skip(
                "stack E2E fora do ar — suba com "
                "`docker compose -f docker-compose.e2e.yml up -d --build` "
                "ou exporte E2E_AUTOSTART=1"
            )
        proc = compose("up", "-d", "--build")
        assert proc.returncode == 0, f"compose up falhou:\n{proc.stderr[-2000:]}"
        started_here = True
    for url in (ORCH, RAG, OBS):
        assert wait_healthy(url), f"{url}/health nunca respondeu 200"
    yield
    if started_here:
        compose("down", "-v", "--remove-orphans")


@pytest.fixture(scope="session")
def client(stack: None) -> Iterator[httpx.Client]:
    with httpx.Client(
        headers={"X-Internal-Key": KEY, "Content-Type": "application/json"},
        timeout=httpx.Timeout(CHAT_TIMEOUT, connect=10.0),
    ) as c:
        yield c


@pytest.fixture(scope="session")
def seeded(client: httpx.Client) -> None:
    """Ingesta documentos golden nas coleções usadas pelos cenários."""
    docs = {
        "financas": [
            {
                "id": "faturamento-trimestre",
                "text": (
                    "# Faturamento e caixa\n\nO faturamento total do trimestre foi de "
                    "R$ 1.250.000,00. O fluxo de caixa do mes fechou positivo em "
                    "R$ 180.000,00. Contas a receber vencidas somam R$ 42.000,00."
                ),
            }
        ],
        "rh": [
            {
                "id": "politica-ferias",
                "text": (
                    "# Politica de ferias\n\nTodo funcionario tem direito a 30 dias de "
                    "ferias por ano apos 12 meses de trabalho. As ferias podem ser "
                    "divididas em ate 3 periodos, sendo um deles de no minimo 14 dias."
                ),
            }
        ],
    }
    for collection, documents in docs.items():
        r = client.post(
            f"{RAG}/v1/ingest",
            json={"collection": collection, "documents": documents},
        )
        assert r.status_code == 200, f"ingest {collection}: {r.status_code} {r.text}"
    # Warm-up: primeira inferencia carrega o modelo no ollama (evita timeout frio).
    warm = client.post(f"{ORCH}/v1/chat", json={"query": "Qual o limite diario de alimentacao em viagens?"})
    assert warm.status_code == 200, f"warm-up: {warm.status_code} {warm.text}"


def chat(client: httpx.Client, query: str, **body: object) -> httpx.Response:
    return client.post(f"{ORCH}/v1/chat", json={"query": query, **body})


def sse_events(resp: httpx.Response) -> list[tuple[str, str]]:
    """Parseia corpo SSE em lista [(event, data), ...]."""
    events: list[tuple[str, str]] = []
    ev = None
    for line in resp.text.splitlines():
        if line.startswith("event: "):
            ev = line[len("event: "):]
        elif line.startswith("data: ") and ev is not None:
            events.append((ev, line[len("data: "):]))
            ev = None
    return events


def sse_json(data: str) -> dict:
    return json.loads(data)
