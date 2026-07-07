"""Upstreams registrados (config v1): serviços do ecossistema + seus /metrics."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Upstream:
    name: str
    url: str


REGISTRY: list[Upstream] = [
    Upstream("svc-guardrails", "http://svc-guardrails:8200/metrics"),
    Upstream("svc-evals", "http://svc-evals:8201/metrics"),
    Upstream("svc-inference", "http://svc-inference:8202/metrics"),
    Upstream("svc-router", "http://svc-router:8203/metrics"),
    Upstream("svc-rag", "http://svc-rag:8204/metrics"),
]


def registry() -> list[Upstream]:
    return list(REGISTRY)
