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
    backend: str = field(default_factory=lambda: os.environ.get("BACKEND", "ollama"))
    backend_url: str = field(
        default_factory=lambda: os.environ.get("BACKEND_URL", "http://localhost:11434")
    )
    default_model: str = field(default_factory=lambda: os.environ.get("DEFAULT_MODEL", ""))
    request_deadline_s: float = field(
        default_factory=lambda: float(os.environ.get("REQUEST_DEADLINE_S", "120"))
    )
    backend_timeout_s: float = field(
        default_factory=lambda: float(os.environ.get("BACKEND_TIMEOUT_S", "60"))
    )
    circuit_fail_threshold: int = field(
        default_factory=lambda: int(os.environ.get("CIRCUIT_FAIL_THRESHOLD", "3"))
    )
    circuit_reset_s: float = field(
        default_factory=lambda: float(os.environ.get("CIRCUIT_RESET_S", "30"))
    )
    rate_limit_per_min: int = field(
        default_factory=lambda: int(os.environ.get("RATE_LIMIT_PER_MIN", "120"))
    )
    otel_enabled: bool = field(default_factory=lambda: _env_bool("OTEL_ENABLED"))
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))


def load_settings() -> Settings:
    return Settings()
