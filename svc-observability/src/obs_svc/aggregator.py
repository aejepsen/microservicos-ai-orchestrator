"""Agregador: raspa upstreams (live), guarda cache stale, ingere eval, deriva estimate."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from obs_svc.model import Metric, Source
from obs_svc.scraper import Scraper
from obs_svc.upstreams import Upstream


@dataclass
class ServiceState:
    name: str
    url: str
    last_scrape: str | None = None
    ok: bool = False
    metrics: list[Metric] = field(default_factory=list)


class Aggregator:
    def __init__(self, upstreams: list[Upstream], scraper: Scraper) -> None:
        self._scraper = scraper
        self._states: dict[str, ServiceState] = {
            u.name: ServiceState(u.name, u.url) for u in upstreams
        }
        self._eval: list[Metric] = []
        self.scrapes_total = 0

    def refresh(self) -> tuple[int, int]:
        """Raspa todos os upstreams. Retorna (ok, failed). Falha não derruba os outros."""
        ok = failed = 0
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        for st in self._states.values():
            self.scrapes_total += 1
            try:
                st.metrics = self._scraper.scrape(st.name, st.url)
                st.ok = True
                st.last_scrape = now
                ok += 1
            except Exception:  # noqa: BLE001 — upstream fora: marca stale, mantém cache
                st.ok = False
                st.metrics = [
                    Metric(m.name, m.value, m.source, m.service, m.unit, m.ts, stale=True)
                    for m in st.metrics
                ]
                failed += 1
        return ok, failed

    def ingest_eval(self, service: str, dataset_date: str, metrics: list[dict]) -> int:
        for m in metrics:
            self._eval.append(
                Metric(str(m["name"]), float(m["value"]), Source.EVAL, service,
                       unit=m.get("unit"), ts=dataset_date)
            )
        return len(metrics)

    def _derived(self, live: list[Metric]) -> list[Metric]:
        """Derivados = ESTIMATE por construção (projeção agregada, não medida)."""
        total_tokens = sum(
            m.value for m in live if m.name in {"tokens_input_total", "tokens_output_total"}
        )
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        return [Metric("ecosystem_tokens_total", total_tokens, Source.ESTIMATE, "ecosystem",
                       unit="{token}", ts=now)]

    def overview(self) -> list[Metric]:
        live = [m for st in self._states.values() for m in st.metrics]
        return live + list(self._eval) + self._derived(live)

    def services(self) -> list[ServiceState]:
        return list(self._states.values())

    def upstreams_up(self) -> int:
        return sum(1 for st in self._states.values() if st.ok)
