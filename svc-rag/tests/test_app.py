from __future__ import annotations

DOCS = {
    "collection": "pol",
    "documents": [
        {"id": "reembolso", "text": "# Reembolso\n\nDespesas de viagem reembolsadas em 30 dias mediante nota."},
        {"id": "ferias", "text": "# Férias\n\nDireito a 30 dias de férias após 12 meses."},
        {"id": "distrator", "text": "# Viagem\n\nViagens de integração anuais. Não trata de reembolso."},
    ],
}


def test_ingest_then_search(client, auth_headers) -> None:
    r = client.post("/v1/ingest", json=DOCS, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["n_chunks"] == 3

    s = client.post("/v1/search", json={"query": "reembolso viagem despesas nota", "collection": "pol"}, headers=auth_headers)
    assert s.status_code == 200
    hits = s.json()["hits"]
    assert hits and hits[0]["doc_id"] == "reembolso"


def test_ingest_idempotent(client, auth_headers) -> None:
    client.post("/v1/ingest", json=DOCS, headers=auth_headers)
    r = client.post("/v1/ingest", json=DOCS, headers=auth_headers)
    assert r.json()["n_skipped_idempotent"] == 3


def test_collections(client, auth_headers) -> None:
    client.post("/v1/ingest", json=DOCS, headers=auth_headers)
    cols = client.get("/v1/collections", headers=auth_headers).json()
    assert any(c["name"] == "pol" and c["n_chunks"] == 3 for c in cols)


def test_doc_too_large(client, auth_headers) -> None:
    big = {"collection": "c", "documents": [{"id": "big", "text": "x" * 100001}]}
    assert client.post("/v1/ingest", json=big, headers=auth_headers).status_code == 422


def test_community_503_when_disabled(client, auth_headers) -> None:
    assert client.get("/v1/community/1", headers=auth_headers).status_code == 503


def test_health(client) -> None:
    b = client.get("/health").json()
    assert b["deps"]["embedder"] == "ok"
    assert b["deps"]["graphrag"] == "absent"


def test_metrics(client, auth_headers) -> None:
    client.post("/v1/ingest", json=DOCS, headers=auth_headers)
    client.post("/v1/search", json={"query": "férias", "collection": "pol"}, headers=auth_headers)
    m = client.get("/metrics", headers=auth_headers).json()
    assert m["ingests_total"] == 1 and m["searches_total"] == 1
    assert m["chunks_total"] == 3 and m["source"] == "live"
