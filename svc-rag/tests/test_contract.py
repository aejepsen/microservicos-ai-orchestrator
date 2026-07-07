from __future__ import annotations

from pathlib import Path

import yaml

SPEC = Path(__file__).resolve().parents[1] / "api" / "openapi.yaml"


def test_openapi_valid() -> None:
    from openapi_spec_validator import validate

    validate(yaml.safe_load(SPEC.read_text()))


def test_all_paths_exercised(client, auth_headers) -> None:
    doc = yaml.safe_load(SPEC.read_text())
    ingest_body = {"documents": [{"id": "d", "text": "# S\n\ncorpo"}]}
    checks = {
        ("post", "/v1/ingest"): lambda: client.post("/v1/ingest", json=ingest_body, headers=auth_headers),
        ("post", "/v1/search"): lambda: client.post("/v1/search", json={"query": "x"}, headers=auth_headers),
        ("get", "/v1/collections"): lambda: client.get("/v1/collections", headers=auth_headers),
        ("get", "/v1/community/{id}"): lambda: client.get("/v1/community/1", headers=auth_headers),
        ("get", "/health"): lambda: client.get("/health"),
        ("get", "/metrics"): lambda: client.get("/metrics", headers=auth_headers),
    }
    declared = {(m, p) for p, item in doc["paths"].items() for m in item}
    assert declared == set(checks), f"YAML != testes: {declared ^ set(checks)}"
    # rota existe = não-404 (community com graphrag off responde 503, não 404)
    for call in checks.values():
        assert call().status_code != 404
