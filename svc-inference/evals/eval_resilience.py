"""G4 — resiliência: circuito abre em falha de transporte; OPEN→503; 4xx NÃO abre (armadilha)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from inference.app import State, create_app  # noqa: E402
from inference.backends import FakeBackend  # noqa: E402
from inference.circuit import CircuitState  # noqa: E402
from inference.config import Settings  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"


def _client(backend: FakeBackend, threshold: int = 3) -> tuple[TestClient, State]:
    s = Settings(internal_key="k", backend="fake", rate_limit_per_min=100000, circuit_fail_threshold=threshold)
    st = State(s, backend)
    return TestClient(create_app(settings=s, state=st)), st


def _post(c: TestClient) -> int:
    return c.post(
        "/v1/chat/completions",
        json={"model": "fake-model", "messages": [{"role": "user", "content": "oi"}]},
        headers={"X-Internal-Key": "k"},
    ).status_code


def main() -> int:
    checks: list[tuple[str, bool]] = []

    # Transporte fora: 3 falhas -> circuito OPEN.
    backend = FakeBackend(fail_transport=True)
    c, st = _client(backend, threshold=3)
    codes = [_post(c) for _ in range(3)]
    checks.append(("transport_503", all(code == 503 for code in codes)))
    checks.append(("circuit_open", st.breaker.state is CircuitState.OPEN))

    # OPEN -> 503 sem bater no backend: conserta o backend, mas circuito segue OPEN.
    backend.fail_transport = False
    checks.append(("open_still_503", _post(c) == 503))

    # ARMADILHA: 4xx do backend NÃO abre o circuito.
    backend_4xx = FakeBackend(fail_business=422)
    c2, st2 = _client(backend_4xx, threshold=3)
    codes_4xx = [_post(c2) for _ in range(5)]
    checks.append(("business_503", all(code == 503 for code in codes_4xx)))
    checks.append(("circuit_stays_closed_on_4xx", st2.breaker.state is CircuitState.CLOSED))

    wrong = [n for n, ok in checks if not ok]
    ok = not wrong
    print(f"[G4] checks={len(checks)} divergencias={len(wrong)} -> {'PASS' if ok else 'FAIL'}")
    for w in wrong:
        print(f"      DIVERGENCIA {w}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"resilience_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "checks": len(checks), "wrong": len(wrong), "pass": ok})
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
