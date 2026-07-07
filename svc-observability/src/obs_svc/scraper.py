"""Scraper de /metrics upstream: adapter (HttpScraper real + FakeScraper gates).

Normaliza o JSON de /metrics de um serviço em métricas com source=live.
Números viram métricas; o campo 'source' do payload upstream é descartado
(a fonte aqui é sempre live — foi raspado de um contador real).
"""

from __future__ import annotations

import time
from typing import Any, Protocol

from obs_svc.model import Metric, Source


class Scraper(Protocol):
    def scrape(self, service: str, url: str) -> list[Metric]: ...


def _flatten(service: str, payload: dict[str, Any]) -> list[Metric]:
    """Converte o JSON de /metrics em métricas live. Ignora 'source' e não-numéricos."""
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    out: list[Metric] = []
    for key, val in payload.items():
        if key == "source":
            continue
        if isinstance(val, bool):
            continue
        if isinstance(val, (int, float)):
            out.append(Metric(key, float(val), Source.LIVE, service, ts=now))
        elif isinstance(val, dict):
            # métricas aninhadas (ex.: by_layer{semantic: 3})
            for sub, subval in val.items():
                if isinstance(subval, (int, float)) and not isinstance(subval, bool):
                    out.append(Metric(f"{key}_{sub}", float(subval), Source.LIVE, service, ts=now))
    return out


class HttpScraper:
    def __init__(self, key: str, timeout_s: float) -> None:
        self._key = key
        self._timeout = timeout_s

    def scrape(self, service: str, url: str) -> list[Metric]:
        import httpx

        headers = {"X-Internal-Key": self._key} if self._key else {}
        resp = httpx.get(url, headers=headers, timeout=self._timeout)
        resp.raise_for_status()
        return _flatten(service, resp.json())


class FakeScraper:
    """Determinístico para gates: payloads fixos por serviço; pode falhar."""

    def __init__(self, payloads: dict[str, dict[str, Any]] | None = None,
                 fail: set[str] | None = None) -> None:
        self._payloads = payloads or {}
        self._fail = fail or set()

    def scrape(self, service: str, url: str) -> list[Metric]:
        if service in self._fail:
            raise ConnectionError(f"fake: {service} fora")
        return _flatten(service, self._payloads.get(service, {}))
