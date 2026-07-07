"""G6 — contrato: OpenAPI válido + toda rota do YAML tem teste de existência."""

from __future__ import annotations

from pathlib import Path

import yaml

SPEC = Path(__file__).resolve().parents[1] / "api" / "openapi.yaml"


def test_openapi_valid() -> None:
    from openapi_spec_validator import validate

    validate(yaml.safe_load(SPEC.read_text()))


def test_all_paths_exercised(client, auth_headers) -> None:
    """Cada rota declarada responde (não-404) — contrato implementado."""
    doc = yaml.safe_load(SPEC.read_text())
    checks = {
        ("post", "/v1/analyze"): lambda: client.post("/v1/analyze", json={"text": "oi"}, headers=auth_headers),
        ("post", "/v1/ood/fit"): lambda: client.post("/v1/ood/fit", json={"in_domain": [], "ood_calibration": []}, headers=auth_headers),
        ("get", "/v1/ood/status"): lambda: client.get("/v1/ood/status", headers=auth_headers),
        ("get", "/health"): lambda: client.get("/health"),
        ("get", "/metrics"): lambda: client.get("/metrics", headers=auth_headers),
    }
    declared = {(m, p) for p, item in doc["paths"].items() for m in item}
    assert declared == set(checks), f"rotas do YAML != rotas testadas: {declared ^ set(checks)}"
    for (_m, _p), call in checks.items():
        assert call().status_code != 404


def test_analyze_response_shape(client, auth_headers) -> None:
    r = client.post("/v1/analyze", json={"text": "Qual o saldo da conta 231?"}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"sanitized_text", "verdicts", "decision", "latency_ms"}
    assert set(body["verdicts"]) == {"injection", "ood"}
    assert body["decision"] in {"allow", "flag", "block"}
