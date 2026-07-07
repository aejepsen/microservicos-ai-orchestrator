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
    embed_model: str = field(
        default_factory=lambda: os.environ.get(
            "EMBED_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
        )
    )
    route_threshold: float = field(
        default_factory=lambda: float(os.environ.get("ROUTE_THRESHOLD", "0.45"))
    )
    tie_margin: float = field(default_factory=lambda: float(os.environ.get("TIE_MARGIN", "0.05")))
    rrf_k: int = field(default_factory=lambda: int(os.environ.get("RRF_K", "60")))
    hybrid_enabled: bool = field(default_factory=lambda: _env_bool("HYBRID_ENABLED", True))
    llm_enabled: bool = field(default_factory=lambda: _env_bool("LLM_ENABLED"))
    llm_url: str = field(default_factory=lambda: os.environ.get("LLM_URL", ""))
    llm_model: str = field(default_factory=lambda: os.environ.get("LLM_MODEL", ""))
    llm_fallback_soft: bool = field(default_factory=lambda: _env_bool("LLM_FALLBACK_SOFT"))
    allow_local_llm: bool = field(default_factory=lambda: _env_bool("ALLOW_LOCAL_LLM"))
    max_query_chars: int = field(
        default_factory=lambda: int(os.environ.get("MAX_QUERY_CHARS", "2000"))
    )
    rate_limit_per_min: int = field(
        default_factory=lambda: int(os.environ.get("RATE_LIMIT_PER_MIN", "120"))
    )
    otel_enabled: bool = field(default_factory=lambda: _env_bool("OTEL_ENABLED"))
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))


def load_settings() -> Settings:
    return Settings()
