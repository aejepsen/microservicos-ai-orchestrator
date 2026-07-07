"""Modelo de métrica normalizada + fonte."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Source(StrEnum):
    LIVE = "live"
    EVAL = "eval"
    ESTIMATE = "estimate"


@dataclass(frozen=True)
class Metric:
    name: str
    value: float
    source: Source
    service: str
    unit: str | None = None
    ts: str | None = None
    stale: bool = False
