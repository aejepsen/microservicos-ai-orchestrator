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
        ("post", "/v1/route"): lambda: client.post("/v1/route", json={"query": "oi"}, headers=auth_headers),
        ("get", "/v1/routes"): lambda: client.get("/v1/routes", headers=auth_headers),
        ("get", "/health"): lambda: client.get("/health"),
        ("get", "/metrics"): lambda: client.get("/metrics", headers=auth_headers),
    }
    declared = {(m, p) for p, item in doc["paths"].items() for m in item}
    assert declared == set(checks), f"YAML != testes: {declared ^ set(checks)}"
    for call in checks.values():
        assert call().status_code != 404
