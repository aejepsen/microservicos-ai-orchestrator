"""Configuração 12-factor via env. Defaults de segurança fail-closed."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

VERSION = "1.0.0"


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "1" if default else "0").strip() in {"1", "true", "True"}


@dataclass(frozen=True)
class Settings:
    internal_key: str = field(default_factory=lambda: os.environ.get("INTERNAL_KEY", ""))
    allow_open_access: bool = field(default_factory=lambda: _env_bool("ALLOW_OPEN_ACCESS"))
    downstream_key: str = field(default_factory=lambda: os.environ.get("DOWNSTREAM_KEY", ""))
    guardrails_url: str = field(
        default_factory=lambda: os.environ.get("GUARDRAILS_URL", "http://svc-guardrails:8200")
    )
    router_url: str = field(
        default_factory=lambda: os.environ.get("ROUTER_URL", "http://svc-router:8203")
    )
    rag_url: str = field(default_factory=lambda: os.environ.get("RAG_URL", "http://svc-rag:8204"))
    inference_url: str = field(
        default_factory=lambda: os.environ.get("INFERENCE_URL", "http://svc-inference:8202")
    )
    model: str = field(default_factory=lambda: os.environ.get("MODEL", "default-model"))
    hitl_enabled: bool = field(default_factory=lambda: _env_bool("HITL_ENABLED"))
    rag_enabled: bool = field(default_factory=lambda: _env_bool("RAG_ENABLED", True))
    max_threads: int = field(default_factory=lambda: int(os.environ.get("MAX_THREADS", "1000")))
    request_deadline_s: float = field(
        default_factory=lambda: float(os.environ.get("REQUEST_DEADLINE_S", "120"))
    )
    downstream_timeout_s: float = field(
        default_factory=lambda: float(os.environ.get("DOWNSTREAM_TIMEOUT_S", "30"))
    )
    circuit_fail_threshold: int = field(
        default_factory=lambda: int(os.environ.get("CIRCUIT_FAIL_THRESHOLD", "3"))
    )
    circuit_reset_s: float = field(
        default_factory=lambda: float(os.environ.get("CIRCUIT_RESET_S", "30"))
    )
    allow_local_downstream: bool = field(
        default_factory=lambda: _env_bool("ALLOW_LOCAL_DOWNSTREAM")
    )
    rate_limit_per_min: int = field(
        default_factory=lambda: int(os.environ.get("RATE_LIMIT_PER_MIN", "120"))
    )
    otel_enabled: bool = field(default_factory=lambda: _env_bool("OTEL_ENABLED"))
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))


def load_settings() -> Settings:
    return Settings()
