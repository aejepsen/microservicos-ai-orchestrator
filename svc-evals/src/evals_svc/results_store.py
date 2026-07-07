"""Persistência append-only de rodadas + agregação cacheada (padrão EvalResultsCollector)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class ResultsStore:
    def __init__(self, results_dir: str, cache_ttl_s: float) -> None:
        self._dir = Path(results_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._ttl = cache_ttl_s
        self._cache: list[dict[str, Any]] | None = None
        self._cache_at = 0.0

    def write(self, suite: str, payload: dict[str, Any]) -> str:
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = self._dir / f"{suite}_{ts}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        self._cache = None  # invalida
        return str(path)

    _REQUIRED = ("suite", "metric", "value", "n_cases", "n_failed_cases")

    def _latest_by_suite(self) -> dict[str, dict[str, Any]]:
        latest: dict[str, tuple[float, dict[str, Any]]] = {}
        for f in self._dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            # Só payloads de rodada; ignora artefatos de eval (engine/scorers/etc).
            if not isinstance(data, dict) or not all(k in data for k in self._REQUIRED):
                continue
            suite = data["suite"]
            mtime = f.stat().st_mtime
            if suite not in latest or mtime > latest[suite][0]:
                latest[suite] = (mtime, data)
        return {s: d for s, (_, d) in latest.items()}

    def aggregate(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if self._cache is not None and now - self._cache_at < self._ttl:
            return self._cache
        self._cache = list(self._latest_by_suite().values())
        self._cache_at = now
        return self._cache

    def by_suite(self, suite: str) -> dict[str, Any] | None:
        return self._latest_by_suite().get(suite)
