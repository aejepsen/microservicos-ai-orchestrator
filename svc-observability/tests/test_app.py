from __future__ import annotations


def test_overview_has_sources(client, auth_headers) -> None:
    r = client.get("/v1/overview", headers=auth_headers)
    assert r.status_code == 200
    sources = {m["source"] for m in r.json()["metrics"]}
    assert "live" in sources and "estimate" in sources  # derivado de tokens


def test_services_status(client, auth_headers) -> None:
    r = client.get("/v1/services", headers=auth_headers)
    assert r.status_code == 200
    names = {s["name"] for s in r.json()}
    assert "svc-router" in names
    assert all(s["ok"] for s in r.json())


def test_refresh(client, auth_headers) -> None:
    r = client.post("/v1/refresh", headers=auth_headers)
    assert r.status_code == 200
    b = r.json()
    assert b["ok"] == 6 and b["failed"] == 0


def test_eval_ingest_shows_in_overview(client, auth_headers) -> None:
    client.post("/v1/eval-results", json={
        "service": "svc-evals", "dataset_date": "2026-07-04",
        "metrics": [{"name": "faithfulness", "value": 0.975}],
    }, headers=auth_headers)
    metrics = client.get("/v1/overview", headers=auth_headers).json()["metrics"]
    faith = [m for m in metrics if m["name"] == "faithfulness"]
    assert faith and faith[0]["source"] == "eval"


def test_prometheus_text(client, auth_headers) -> None:
    r = client.get("/v1/prometheus", headers=auth_headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "# TYPE" in r.text and 'source="' in r.text


def test_health_ok_when_all_up(client) -> None:
    b = client.get("/health").json()
    assert b["deps"]["upstreams_up"] == 6
    assert b["status"] == "ok"


def test_metrics(client, auth_headers) -> None:
    client.get("/v1/overview", headers=auth_headers)
    m = client.get("/metrics", headers=auth_headers).json()
    assert m["source"] == "live"
    assert m["overviews_total"] >= 1
    assert m["upstreams_up"] == 6
