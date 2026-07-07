"""Schemas Pydantic v2 — espelham api/openapi.yaml."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    thread_id: str | None = None
    stream: bool = False
    allow_write: bool = False


class AgentResult(BaseModel):
    domain: str
    answer: str
    context_used: int


class ChatResponse(BaseModel):
    thread_id: str
    decision: Literal["answered", "blocked", "paused"]
    domains: list[str]
    agents: list[AgentResult]
    final: str | None = None
    pending_write: dict[str, Any] | None = None


class ResumeRequest(BaseModel):
    approve: bool


class ThreadState(BaseModel):
    thread_id: str
    decision: Literal["answered", "blocked", "paused"]
    final: str | None = None
    pending_write: dict[str, Any] | None = None


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    deps: dict[str, str]


class Metrics(BaseModel):
    source: Literal["live"] = "live"
    chats_total: int
    blocked_total: int
    paused_total: int
    by_domain: dict[str, int]
    latency_ms_p50: float
    latency_ms_p95: float

