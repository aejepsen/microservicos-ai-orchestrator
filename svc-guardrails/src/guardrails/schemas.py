"""Schemas Pydantic v2 — espelham api/openapi.yaml (fonte da verdade)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Check = Literal["sanitize", "injection", "ood"]


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1)
    checks: list[Check] = ["sanitize", "injection", "ood"]
    context: str | None = None


class InjectionVerdictModel(BaseModel):
    flagged: bool
    score: float
    patterns: list[str]


class OodVerdictModel(BaseModel):
    flagged: bool
    residual: float
    threshold: float


class Verdicts(BaseModel):
    injection: InjectionVerdictModel | None
    ood: OodVerdictModel | None


class AnalyzeResponse(BaseModel):
    sanitized_text: str
    verdicts: Verdicts
    decision: Literal["allow", "flag", "block"]
    latency_ms: float


class FitSample(BaseModel):
    text: str
    is_clarification: bool = False


class OodFitRequest(BaseModel):
    in_domain: list[FitSample] = Field(min_length=30)
    ood_calibration: list[str] = Field(min_length=10)


class OodFitResponse(BaseModel):
    n_samples: int
    n_rejected_clarification: int
    threshold: float
    auc_loo: float
    corpus_hash: str


class OodStatus(BaseModel):
    fitted: bool
    n_samples: int | None = None
    threshold: float | None = None
    auc_loo: float | None = None
    fitted_at: str | None = None
    corpus_hash: str | None = None


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    deps: dict[str, str]


class Metrics(BaseModel):
    source: Literal["live"] = "live"
    analyses_total: int
    blocks_total: int
    flags_total: int
    latency_ms_p50: float
    latency_ms_p95: float


class BusinessError(BaseModel):
    error: str
    detail: str
    rule: str
