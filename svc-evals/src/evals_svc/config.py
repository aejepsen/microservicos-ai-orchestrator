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
    results_dir: str = field(default_factory=lambda: os.environ.get("RESULTS_DIR", "evals/results"))
    results_cache_ttl_s: float = field(
        default_factory=lambda: float(os.environ.get("RESULTS_CACHE_TTL_S", "10"))
    )
    judge_enabled: bool = field(default_factory=lambda: _env_bool("JUDGE_ENABLED"))
    judge_url: str = field(default_factory=lambda: os.environ.get("JUDGE_URL", ""))
    judge_model: str = field(default_factory=lambda: os.environ.get("JUDGE_MODEL", ""))
    judge_timeout_s: float = field(
        default_factory=lambda: float(os.environ.get("JUDGE_TIMEOUT_S", "30"))
    )
    target_deadline_s: float = field(
        default_factory=lambda: float(os.environ.get("TARGET_DEADLINE_S", "10"))
    )
    allow_local_target: bool = field(default_factory=lambda: _env_bool("ALLOW_LOCAL_TARGET"))
    rate_limit_per_min: int = field(
        default_factory=lambda: int(os.environ.get("RATE_LIMIT_PER_MIN", "120"))
    )
    otel_enabled: bool = field(default_factory=lambda: _env_bool("OTEL_ENABLED"))
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))


def load_settings() -> Settings:
    return Settings()
