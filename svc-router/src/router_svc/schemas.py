"""Schemas Pydantic v2 — espelham api/openapi.yaml."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RouteDef(BaseModel):
    name: str
    exemplars: list[str] = Field(min_length=1)


class RouteRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    allow_llm: bool = True
    top_k: int = 3
    routes_override: list[RouteDef] | None = None


class RoutePlan(BaseModel):
    domains: list[str] = Field(min_length=1)
    layer: Literal["semantic", "lexical", "llm", "fallback"]
    scores: dict[str, float]
    llm_used: bool


class RouteInfo(BaseModel):
    name: str
    n_exemplars: int
    n_guards: int


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    deps: dict[str, str]


class Metrics(BaseModel):
    source: Literal["live"] = "live"
    routes_total: int
    by_layer: dict[str, int]
    latency_ms_p50: float
    latency_ms_p95: float


class BusinessError(BaseModel):
    error: str
    detail: str
    rule: str
