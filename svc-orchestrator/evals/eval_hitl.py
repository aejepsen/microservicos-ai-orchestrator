"""G3 — HITL write-intent: escrita pausa; leitura não; ARMADILHA nominal; resume."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orch_svc.clients import FakeGuardrails, FakeInference, FakeRag, FakeRouter  # noqa: E402
from orch_svc.orchestrator import Breakers, Orchestrator, Thread  # noqa: E402
from orch_svc.write_intent import is_write_intent  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"


def _orch():
    return Orchestrator(
        FakeGuardrails(), FakeRouter(["financas"]), FakeRag(), FakeInference(),
        Breakers(3, 30), hitl_enabled=True,
    )


def main() -> int:
    checks: list[tuple[str, bool]] = []

    # write_intent puro.
    checks.append(("write_cadastrar", is_write_intent("Cadastre um novo funcionário")))
    checks.append(("write_pagar", is_write_intent("Pague a conta 231")))
    checks.append(("write_atualizar", is_write_intent("Atualize o salário do 210")))
    # leitura não é escrita.
    checks.append(("read_saldo", not is_write_intent("Qual o saldo da conta?")))
    checks.append(("read_liste", not is_write_intent("Liste os pedidos do vendedor")))
    # ARMADILHA: frase nominal "contas a pagar" NÃO é escrita.
    checks.append(("armadilha_contas_pagar", not is_write_intent("Qual o total de contas a pagar?")))
    checks.append(("armadilha_relatorio", not is_write_intent("Gere o relatório de contas a pagar")))

    # Fluxo: escrita pausa.
    o = _orch()
    t = Thread("t1", "Cadastre um funcionário no RH")
    evs = [e.type for e in o.run(t, "00-a-b-01", allow_write=False)]
    checks.append(("write_pauses", "paused" in evs and t.decision == "paused"))
    checks.append(("no_final_when_paused", t.final is None))

    # Resume(approve) conclui.
    evs2 = [e.type for e in o.resume(t, "00-a-b-01", approve=True)]
    checks.append(("resume_finalizes", "final" in evs2 and t.decision == "answered"))

    # Resume(reject) recusa.
    t2 = Thread("t2", "Delete o produto X")
    list(o.run(t2, "00-a-b-01", allow_write=False))
    list(o.resume(t2, "00-a-b-01", approve=False))
    checks.append(("resume_reject", "rejeitada" in (t2.final or "")))

    # allow_write=True não pausa.
    t3 = Thread("t3", "Cadastre um funcionário")
    evs3 = [e.type for e in o.run(t3, "00-a-b-01", allow_write=True)]
    checks.append(("allow_write_no_pause", "paused" not in evs3 and "final" in evs3))

    wrong = [n for n, ok in checks if not ok]
    passed = not wrong
    print(f"[G3] checks={len(checks)} divergencias={len(wrong)} -> {'PASS' if passed else 'FAIL'}")
    for w in wrong:
        print(f"      DIVERGENCIA {w}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"hitl_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "checks": len(checks), "wrong": len(wrong), "pass": passed})
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
