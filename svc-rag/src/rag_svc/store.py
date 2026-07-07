"""Vector store: interface + InMemoryStore (gates) + QdrantStore (prod, httpx REST).

Idempotência: chunk_id = sha256(doc_id + index + conteúdo)[:16]. Reingerir o
mesmo conteúdo é no-op.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from rag_svc.embedder import cosine


@dataclass(frozen=True)
class StoredChunk:
    chunk_id: str
    doc_id: str
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    doc_id: str
    text: str
    score: float
    metadata: dict[str, Any]


def chunk_id(doc_id: str, index: int, content: str) -> str:
    return hashlib.sha256(f"{doc_id}|{index}|{content}".encode()).hexdigest()[:16]


class VectorStore(Protocol):
    def upsert(self, collection: str, chunks: list[StoredChunk], vectors: np.ndarray) -> int: ...
    def search(self, collection: str, qvec: np.ndarray, top_k: int) -> list[Hit]: ...
    def count(self, collection: str) -> int: ...
    def collections(self) -> list[str]: ...


@dataclass
class InMemoryStore:
    """dict por coleção: chunk_id -> (StoredChunk, vetor). numpy cosseno."""

    _data: dict[str, dict[str, tuple[StoredChunk, np.ndarray]]] = field(default_factory=dict)

    def upsert(self, collection: str, chunks: list[StoredChunk], vectors: np.ndarray) -> int:
        col = self._data.setdefault(collection, {})
        added = 0
        for ch, vec in zip(chunks, vectors, strict=True):
            if ch.chunk_id in col:
                continue  # idempotente
            col[ch.chunk_id] = (ch, vec)
            added += 1
        return added

    def search(self, collection: str, qvec: np.ndarray, top_k: int) -> list[Hit]:
        col = self._data.get(collection, {})
        scored = [
            Hit(ch.chunk_id, ch.doc_id, ch.text, cosine(qvec, vec), ch.metadata)
            for ch, vec in col.values()
        ]
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]

    def count(self, collection: str) -> int:
        return len(self._data.get(collection, {}))

    def collections(self) -> list[str]:
        return list(self._data)


@dataclass
class QdrantStore:
    """Backend Qdrant via httpx REST (sem cliente pesado). Auth por API key."""

    url: str
    api_key: str
    timeout_s: float = 10.0

    def _headers(self) -> dict[str, str]:
        return {"api-key": self.api_key} if self.api_key else {}

    def _client(self) -> Any:
        import httpx

        return httpx.Client(
            base_url=self.url.rstrip("/"), timeout=self.timeout_s, headers=self._headers()
        )

    def _ensure(self, client: Any, collection: str, dim: int) -> None:
        r = client.get(f"/collections/{collection}")
        if r.status_code == 404:
            client.put(
                f"/collections/{collection}",
                json={"vectors": {"size": dim, "distance": "Cosine"}},
            )

    def upsert(self, collection: str, chunks: list[StoredChunk], vectors: np.ndarray) -> int:
        with self._client() as c:
            self._ensure(c, collection, vectors.shape[1])
            points = [
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_URL, ch.chunk_id)),
                    "vector": vec.tolist(),
                    "payload": {
                        "chunk_id": ch.chunk_id,
                        "doc_id": ch.doc_id,
                        "text": ch.text,
                        "metadata": ch.metadata,
                    },
                }
                for ch, vec in zip(chunks, vectors, strict=True)
            ]
            r = c.put(
                f"/collections/{collection}/points",
                params={"wait": "true"},
                json={"points": points},
            )
            r.raise_for_status()
        return len(points)

    def search(self, collection: str, qvec: np.ndarray, top_k: int) -> list[Hit]:
        with self._client() as c:
            r = c.post(
                f"/collections/{collection}/points/search",
                json={"vector": qvec.tolist(), "limit": top_k, "with_payload": True},
            )
            r.raise_for_status()
        hits = []
        for item in r.json().get("result", []):
            p = item.get("payload", {})
            hits.append(Hit(p.get("chunk_id", str(item["id"])), p.get("doc_id", ""),
                            p.get("text", ""), float(item["score"]), p.get("metadata", {})))
        return hits

    def count(self, collection: str) -> int:
        with self._client() as c:
            r = c.post(f"/collections/{collection}/points/count", json={})
        return int(r.json().get("result", {}).get("count", 0))

    def collections(self) -> list[str]:
        with self._client() as c:
            r = c.get("/collections")
        return [x["name"] for x in r.json().get("result", {}).get("collections", [])]
