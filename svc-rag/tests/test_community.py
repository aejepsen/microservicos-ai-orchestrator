from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from rag_svc.app import State, create_app
from rag_svc.community import CommunityStore
from rag_svc.config import Settings
from rag_svc.embedder import FakeEmbedder
from rag_svc.store import InMemoryStore

ARTIFACT = {"communities": [
    {"id": "1", "title": "Finanças", "summary": "resumo fin", "members": ["reembolso", "alcada"]},
]}


def _write_artifact(tmp_path: Path) -> None:
    (tmp_path / "communities.json").write_text(json.dumps(ARTIFACT))


def test_community_store_loads(tmp_path: Path) -> None:
    _write_artifact(tmp_path)
    cs = CommunityStore(str(tmp_path))
    assert cs.available
    assert cs.get("1")["title"] == "Finanças"


def test_community_absent_when_no_artifact(tmp_path: Path) -> None:
    assert not CommunityStore(str(tmp_path)).available


def test_community_endpoint_served(tmp_path: Path) -> None:
    _write_artifact(tmp_path)
    s = Settings(internal_key="k", vector_store="memory", rate_limit_per_min=100000,
                 graphrag_enabled=True, models_dir=str(tmp_path))
    c = TestClient(create_app(settings=s, state=State(s, FakeEmbedder(), InMemoryStore())))
    r = c.get("/v1/community/1", headers={"X-Internal-Key": "k"})
    assert r.status_code == 200
    assert r.json()["title"] == "Finanças"


def test_community_404(tmp_path: Path) -> None:
    _write_artifact(tmp_path)
    s = Settings(internal_key="k", vector_store="memory", rate_limit_per_min=100000,
                 graphrag_enabled=True, models_dir=str(tmp_path))
    c = TestClient(create_app(settings=s, state=State(s, FakeEmbedder(), InMemoryStore())))
    assert c.get("/v1/community/999", headers={"X-Internal-Key": "k"}).status_code == 404
