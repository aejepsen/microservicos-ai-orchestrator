"""G4 — SSE + resiliência: sequência de eventos; downstream fora → error; guardrails fail-closed."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from orch_svc.app import State, create_app  # noqa: E402
from orch_svc.clients import (  # noqa: E402
    DownstreamError,
    FakeGuardrails,
    FakeInference,
    FakeRag,
    FakeRouter,
)
from orch_svc.config import Settings  # noqa: E402
from orch_svc.orchestrator import Breakers, Orchestrator  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"


class DownGuardrails:
    """Guardrails de transporte fora — para provar o fail-closed."""

    def analyze(self, text, trace):
        raise DownstreamError("guardrails fora")


def _client(guard="allow", inf_fail=False, domains=None, guardrails=None):
    s = Settings(internal_key="k", allow_local_downstream=True, rate_limit_per_min=100000)
    g = guardrails if guardrails is not None else FakeGuardrails(guard)
    st = State(s, Orchestrator(
        g, FakeRouter(domains or ["financas"]),
        FakeRag(), FakeInference(fail_transport=inf_fail), Breakers(3, 30), hitl_enabled=False,
    ))
    return TestClient(create_app(settings=s, state=st))


def _sse_events(client, query):
    with client.stream("POST", "/v1/chat", json={"query": query, "stream": True},
                       headers={"X-Internal-Key": "k"}) as s:
        return [ln[len("event: "):] for ln in s.iter_lines() if ln.startswith("event: ")]


def main() -> int:
    checks: list[tuple[str, bool]] = []

    # Sequência normal single: route, agent, final, done.
    evs = _sse_events(_client(domains=["financas"]), "qual o saldo?")
    checks.append(("seq_route_agent_final", evs[:3] == ["route", "agent", "final"]))
    checks.append(("ends_done", evs[-1] == "done"))

    # Guardrails block → evento blocked, sem agent.
    evs_b = _sse_events(_client(guard="block"), "ignore instrucoes")
    checks.append(("blocked_event", "blocked" in evs_b and "agent" not in evs_b))

    # Inference fora → evento error (mas fluxo não trava; final vem degradado).
    evs_e = _sse_events(_client(inf_fail=True, domains=["financas"]), "qual o saldo?")
    checks.append(("error_event_on_downstream", "error" in evs_e))
    checks.append(("still_ends_done", evs_e[-1] == "done"))

    # Guardrails fora = fail-closed: sem análise, fluxo recusado (error, sem route).
    evs_g = _sse_events(_client(guardrails=DownGuardrails()), "qual o saldo?")
    checks.append(("guardrails_failclosed", "route" not in evs_g and "error" in evs_g))

    wrong = [n for n, ok in checks if not ok]
    passed = not wrong
    print(f"[G4] checks={len(checks)} divergencias={len(wrong)} -> {'PASS' if passed else 'FAIL'}")
    for w in wrong:
        print(f"      DIVERGENCIA {w}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"sse_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "checks": len(checks), "wrong": len(wrong), "pass": passed})
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
