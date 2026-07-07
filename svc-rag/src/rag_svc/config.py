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
    vector_store: str = field(default_factory=lambda: os.environ.get("VECTOR_STORE", "qdrant"))
    qdrant_url: str = field(
        default_factory=lambda: os.environ.get("QDRANT_URL", "http://localhost:6333")
    )
    qdrant_api_key: str = field(default_factory=lambda: os.environ.get("QDRANT_API_KEY", ""))
    allow_local_store: bool = field(default_factory=lambda: _env_bool("ALLOW_LOCAL_STORE"))
    chunk_max_chars: int = field(
        default_factory=lambda: int(os.environ.get("CHUNK_MAX_CHARS", "800"))
    )
    chunk_overlap: int = field(default_factory=lambda: int(os.environ.get("CHUNK_OVERLAP", "100")))
    graphrag_enabled: bool = field(default_factory=lambda: _env_bool("GRAPHRAG_ENABLED"))
    max_doc_chars: int = field(
        default_factory=lambda: int(os.environ.get("MAX_DOC_CHARS", "100000"))
    )
    models_dir: str = field(default_factory=lambda: os.environ.get("MODELS_DIR", "models"))
    rate_limit_per_min: int = field(
        default_factory=lambda: int(os.environ.get("RATE_LIMIT_PER_MIN", "120"))
    )
    otel_enabled: bool = field(default_factory=lambda: _env_bool("OTEL_ENABLED"))
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))


def load_settings() -> Settings:
    return Settings()
