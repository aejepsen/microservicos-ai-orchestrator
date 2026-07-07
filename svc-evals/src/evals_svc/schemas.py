"""Schemas Pydantic v2 — espelham api/openapi.yaml."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Comparator = Literal[">=", ">", "<=", "<", "=="]
Source = Literal["live", "eval", "estimate"]


class GateSpec(BaseModel):
    metric: str
    comparator: Comparator
    threshold: float


class TargetSpec(BaseModel):
    url: str
    method: str = "POST"
    input_field: str
    output_pointer: str


class RunRequest(BaseModel):
    suite: str | None = None
    golden_inline: list[dict[str, Any]] | None = None
    scorer: str | None = None
    scorer_params: dict[str, Any] = Field(default_factory=dict)
    gate: GateSpec | None = None
    mode: Literal["offline", "live"] = "offline"
    target: TargetSpec | None = None
    source: Source = "eval"


class RunResponse(BaseModel):
    suite: str
    metric: str
    value: float
    gate: GateSpec | None
    passed: bool | None
    n_cases: int
    n_failed_cases: int
    source: Source
    ran_at: str
    artifact_path: str


class SuiteInfo(BaseModel):
    name: str
    scorer: str
    metric: str
    gate: GateSpec | None


class ResultsAggregate(BaseModel):
    results: list[RunResponse]


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    deps: dict[str, str]


class Metrics(BaseModel):
    source: Literal["live"] = "live"
    runs_total: int
    gates_pass_total: int
    gates_fail_total: int
    latency_ms_p50: float
    latency_ms_p95: float


class BusinessError(BaseModel):
    error: str
    detail: str
    rule: str
