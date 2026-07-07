from __future__ import annotations


def test_route_endpoint(client, auth_headers) -> None:
    r = client.post("/v1/route", json={"query": "Qual a comissão do vendedor?"}, headers=auth_headers)
    assert r.status_code == 200
    b = r.json()
    assert set(b) == {"domains", "layer", "scores", "llm_used"}
    assert "vendas" in b["domains"] and "financas" in b["domains"]


def test_route_layers_reported(client, auth_headers) -> None:
    r = client.post("/v1/route", json={"query": "Qual a comissão?"}, headers=auth_headers)
    assert r.json()["layer"] in {"semantic", "lexical", "llm", "fallback"}


def test_routes_override(client, auth_headers) -> None:
    r = client.post(
        "/v1/route",
        json={"query": "alpha", "routes_override": [
            {"name": "x", "exemplars": ["alpha um", "alpha dois"]},
            {"name": "y", "exemplars": ["beta um"]},
        ]},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert set(r.json()["scores"]) == {"x", "y"}


def test_query_too_long(client, auth_headers) -> None:
    r = client.post("/v1/route", json={"query": "a" * 3000}, headers=auth_headers)
    assert r.status_code == 422


def test_list_routes(client, auth_headers) -> None:
    r = client.get("/v1/routes", headers=auth_headers)
    assert r.status_code == 200
    names = {x["name"] for x in r.json()}
    assert {"financas", "rh", "estoque", "vendas"} <= names


def test_health(client) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["deps"]["embedder"] == "ok"


def test_metrics_by_layer(client, auth_headers) -> None:
    client.post("/v1/route", json={"query": "Qual a comissão do vendedor?"}, headers=auth_headers)
    m = client.get("/metrics", headers=auth_headers).json()
    assert m["routes_total"] == 1
    assert sum(m["by_layer"].values()) == 1
    assert m["source"] == "live"
