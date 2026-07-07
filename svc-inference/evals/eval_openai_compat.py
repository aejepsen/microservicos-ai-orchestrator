"""G2 — compatibilidade OpenAI: envelope bloqueante + chunks de stream + [DONE]."""

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


def _client() -> TestClient:
    settings = Settings(internal_key="k", backend="fake", rate_limit_per_min=100000)
    return TestClient(create_app(settings=settings, state=State(settings, FakeBackend())))


def main() -> int:
    c = _client()
    h = {"X-Internal-Key": "k"}
    checks: list[tuple[str, bool]] = []

    # Bloqueante: envelope OpenAI.
    r = c.post("/v1/chat/completions", json={"model": "fake-model", "messages": [{"role": "user", "content": "oi"}]}, headers=h)
    body = r.json()
    checks.append(("status_200", r.status_code == 200))
    checks.append(("object_chat_completion", body.get("object") == "chat.completion"))
    checks.append(("has_choices", len(body.get("choices", [])) == 1))
    checks.append(("finish_reason", body["choices"][0]["finish_reason"] == "stop"))
    checks.append(("has_usage", set(body.get("usage", {})) == {"prompt_tokens", "completion_tokens", "total_tokens"}))
    checks.append(("id_prefix", str(body.get("id", "")).startswith("chatcmpl-")))

    # Streaming: chunks + usage no último + [DONE].
    with c.stream("POST", "/v1/chat/completions", json={"model": "fake-model", "stream": True, "messages": [{"role": "user", "content": "oi"}]}, headers=h) as s:
        lines = [ln for ln in s.iter_lines() if ln]
    payloads = [ln[len("data: "):] for ln in lines if ln.startswith("data: ")]
    checks.append(("stream_done", payloads[-1] == "[DONE]"))
    chunks = [json.loads(p) for p in payloads if p != "[DONE]"]
    checks.append(("chunk_object", all(ch["object"] == "chat.completion.chunk" for ch in chunks)))
    checks.append(("usage_last_chunk", "usage" in chunks[-1] and "usage" not in chunks[0]))
    checks.append(("final_finish_reason", chunks[-1]["choices"][0]["finish_reason"] == "stop"))

    wrong = [n for n, ok in checks if not ok]
    ok = not wrong
    print(f"[G2] checks={len(checks)} divergencias={len(wrong)} -> {'PASS' if ok else 'FAIL'}")
    for w in wrong:
        print(f"      DIVERGENCIA {w}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"compat_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "checks": len(checks), "wrong": len(wrong), "pass": ok})
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
