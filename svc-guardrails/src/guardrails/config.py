"""Configuração 12-factor via env. Defaults de segurança são fail-closed."""

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
    ood_action: str = field(default_factory=lambda: os.environ.get("OOD_ACTION", "flag"))
    ood_required: bool = field(default_factory=lambda: _env_bool("OOD_REQUIRED"))
    max_text_chars: int = field(
        default_factory=lambda: int(os.environ.get("MAX_TEXT_CHARS", "8000"))
    )
    rate_limit_per_min: int = field(
        default_factory=lambda: int(os.environ.get("RATE_LIMIT_PER_MIN", "120"))
    )
    otel_enabled: bool = field(default_factory=lambda: _env_bool("OTEL_ENABLED"))
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))
    log_text_preview: bool = field(default_factory=lambda: _env_bool("LOG_TEXT_PREVIEW"))
    models_dir: str = field(default_factory=lambda: os.environ.get("MODELS_DIR", "models"))
    request_deadline_s: float = field(
        default_factory=lambda: float(os.environ.get("REQUEST_DEADLINE_S", "10"))
    )

    def auth_enabled(self) -> bool:
        """Fail-closed: sem key e sem opt-in explícito de modo aberto, tudo bloqueia."""
        return not (self.allow_open_access and not self.internal_key) or bool(self.internal_key)


def load_settings() -> Settings:
    return Settings()
