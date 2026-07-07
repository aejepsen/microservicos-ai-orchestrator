"""Schemas Pydantic v2 — espelham api/openapi.yaml."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Document(BaseModel):
    id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestRequest(BaseModel):
    collection: str = "default"
    documents: list[Document] = Field(min_length=1)


class IngestResponse(BaseModel):
    collection: str
    n_documents: int
    n_chunks: int
    n_skipped_idempotent: int


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    collection: str = "default"
    top_k: int = 3


class Hit(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    collection: str
    hits: list[Hit]


class CollectionInfo(BaseModel):
    name: str
    n_chunks: int


class CommunitySummary(BaseModel):
    id: str
    title: str
    summary: str
    members: list[str]


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    deps: dict[str, str]


class Metrics(BaseModel):
    source: Literal["live"] = "live"
    ingests_total: int
    searches_total: int
    chunks_total: int
    latency_ms_p50: float
    latency_ms_p95: float


class BusinessError(BaseModel):
    error: str
    detail: str
    rule: str
