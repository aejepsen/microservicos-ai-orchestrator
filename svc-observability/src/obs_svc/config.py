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
    upstream_key: str = field(default_factory=lambda: os.environ.get("UPSTREAM_KEY", ""))
    scrape_timeout_s: float = field(
        default_factory=lambda: float(os.environ.get("SCRAPE_TIMEOUT_S", "5"))
    )
    overview_cache_ttl_s: float = field(
        default_factory=lambda: float(os.environ.get("OVERVIEW_CACHE_TTL_S", "10"))
    )
    scrape_interval_s: float = field(
        default_factory=lambda: float(os.environ.get("SCRAPE_INTERVAL_S", "0"))
    )
    allow_local_upstream: bool = field(default_factory=lambda: _env_bool("ALLOW_LOCAL_UPSTREAM"))
    rate_limit_per_min: int = field(
        default_factory=lambda: int(os.environ.get("RATE_LIMIT_PER_MIN", "120"))
    )
    otel_enabled: bool = field(default_factory=lambda: _env_bool("OTEL_ENABLED"))
    otlp_metrics_enabled: bool = field(default_factory=lambda: _env_bool("OTLP_METRICS_ENABLED"))
    otlp_metrics_interval_s: float = field(
        default_factory=lambda: float(os.environ.get("OTLP_METRICS_INTERVAL_S", "60"))
    )
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))


def load_settings() -> Settings:
    return Settings()
