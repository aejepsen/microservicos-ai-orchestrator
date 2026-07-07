"""G3 — tokens na fonte: usage do backend propaga à resposta E às métricas."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from inference.app import State, create_app  # noqa: E402
from inference.backends import FakeBackend  # noqa: E402
from inference.config import Settings  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"


def main() -> int:
    settings = Settings(internal_key="k", backend="fake", rate_limit_per_min=100000)
    # reply com 5 palavras -> completion_tokens=5 determinístico.
    backend = FakeBackend(reply="um dois tres quatro cinco")
    c = TestClient(create_app(settings=settings, state=State(settings, backend)))
    h = {"X-Internal-Key": "k"}
    checks: list[tuple[str, bool]] = []

    prompt = "palavra1 palavra2 palavra3"  # 3 tokens
    r = c.post("/v1/chat/completions", json={"model": "fake-model", "messages": [{"role": "user", "content": prompt}]}, headers=h)
    usage = r.json()["usage"]
    checks.append(("prompt_tokens_source", usage["prompt_tokens"] == 3))
    checks.append(("completion_tokens_source", usage["completion_tokens"] == 5))
    checks.append(("total_consistent", usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]))

    # Propagação às métricas.
    m = c.get("/metrics", headers=h).json()
    checks.append(("metrics_input", m["tokens_input_total"] == 3))
    checks.append(("metrics_output", m["tokens_output_total"] == 5))
    checks.append(("metrics_source_live", m["source"] == "live"))
    checks.append(("requests_counted", m["requests_total"] == 1))

    wrong = [n for n, ok in checks if not ok]
    ok = not wrong
    print(f"[G3] checks={len(checks)} divergencias={len(wrong)} usage={usage} -> {'PASS' if ok else 'FAIL'}")
    for w in wrong:
        print(f"      DIVERGENCIA {w}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"usage_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "checks": len(checks), "wrong": len(wrong), "pass": ok})
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
