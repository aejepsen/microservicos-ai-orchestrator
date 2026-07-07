from __future__ import annotations

from pathlib import Path

import yaml

SPEC = Path(__file__).resolve().parents[1] / "api" / "openapi.yaml"


def test_openapi_valid() -> None:
    from openapi_spec_validator import validate

    validate(yaml.safe_load(SPEC.read_text()))


def test_all_paths_exercised(client, auth_headers) -> None:
    doc = yaml.safe_load(SPEC.read_text())
    checks = {
        ("post", "/v1/run"): lambda: client.post("/v1/run", json={"suite": "routing_accuracy"}, headers=auth_headers),
        ("get", "/v1/suites"): lambda: client.get("/v1/suites", headers=auth_headers),
        ("get", "/v1/results"): lambda: client.get("/v1/results", headers=auth_headers),
        ("get", "/v1/results/{suite}"): lambda: client.get("/v1/results/routing_accuracy", headers=auth_headers),
        ("get", "/health"): lambda: client.get("/health"),
        ("get", "/metrics"): lambda: client.get("/metrics", headers=auth_headers),
    }
    declared = {(m, p) for p, item in doc["paths"].items() for m in item}
    assert declared == set(checks), f"YAML != testes: {declared ^ set(checks)}"
    for call in checks.values():
        assert call().status_code != 404


def test_run_offline_gate(client, auth_headers) -> None:
    r = client.post("/v1/run", json={"suite": "routing_accuracy"}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["metric"] == "macro_f1"
    assert body["passed"] is True
    assert body["source"] == "eval"


def test_run_inline(client, auth_headers) -> None:
    r = client.post(
        "/v1/run",
        json={
            "golden_inline": [{"expected": "a", "response": "a"}, {"expected": "b", "response": "x"}],
            "scorer": "exact_match",
            "gate": {"metric": "pass_rate", "comparator": ">=", "threshold": 0.9},
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["passed"] is False  # 0.5 < 0.9
