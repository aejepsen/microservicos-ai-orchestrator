"""Schemas Pydantic v2 — espelham api/openapi.yaml."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MetricModel(BaseModel):
    name: str
    value: float
    source: Literal["live", "eval", "estimate"]
    service: str
    unit: str | None = None
    ts: str | None = None
    stale: bool = False


class Overview(BaseModel):
    generated_at: str
    metrics: list[MetricModel]


class ServiceStatus(BaseModel):
    name: str
    url: str
    last_scrape: str | None = None
    ok: bool
    n_metrics: int


class RefreshResponse(BaseModel):
    scraped: int
    ok: int
    failed: int


class EvalMetricIn(BaseModel):
    name: str
    value: float
    unit: str | None = None


class EvalResultIn(BaseModel):
    service: str
    dataset_date: str
    metrics: list[EvalMetricIn] = Field(min_length=1)


class EvalResultResponse(BaseModel):
    ingested: int


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    deps: dict[str, int]


class Metrics(BaseModel):
    source: Literal["live"] = "live"
    scrapes_total: int
    overviews_total: int
    upstreams_up: int
    latency_ms_p50: float
    latency_ms_p95: float


class BusinessError(BaseModel):
    error: str
    detail: str
    rule: str
