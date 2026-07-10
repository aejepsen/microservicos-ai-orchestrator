"""D7 — Export OTLP de métricas agregadas (push opt-in para SaaS).

OTLP_METRICS_ENABLED=0 (default): no-op absoluto — on-premise puro, gates
offline intactos. OTLP_METRICS_ENABLED=1: MeterProvider + exporter OTLP HTTP;
cada métrica agregada vira ObservableGauge com atributos service/source/stale
— a fonte viaja junto (D3 é inegociável também no export). Endpoint e auth
pelas envs padrão OTel (OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_EXPORTER_OTLP_HEADERS).
Fail-open: SaaS fora → warning em thread de export, nunca bloqueia scrape/API
(espelho do fail-closed de entrada).
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("obs")

_SERVICE_NAME = "svc-observability"


class MetricsExport:
    """Registra ObservableGauges por nome de métrica agregada (lazy).

    Nomes novos aparecem quando upstreams/evals trazem métricas inéditas;
    `sync()` deve ser chamado após refresh/ingest — instrumento criado passa
    a ser coletado no ciclo de export seguinte.
    """

    def __init__(
        self, agg: Any, meter: Any, sanitize: Callable[[str], str], provider: Any = None
    ) -> None:
        self._agg = agg
        self._meter = meter
        self._sanitize = sanitize
        self._provider = provider
        self._known: set[str] = set()
        self._lock = threading.Lock()

    def close(self) -> None:
        """Encerra o export em background (flush final com timeout curto)."""
        if self._provider is not None:
            try:
                self._provider.shutdown(timeout_millis=2000)
            except Exception as exc:  # noqa: BLE001 — shutdown nunca propaga (D7)
                logger.debug("shutdown do export OTLP: %s", exc)

    def _callback_for(self, name: str) -> Callable[[Any], list[Any]]:
        def cb(_options: Any) -> list[Any]:
            from opentelemetry.metrics import Observation

            return [
                Observation(
                    m.value,
                    {"service": m.service, "source": str(m.source), "stale": m.stale},
                )
                for m in self._agg.overview()
                if m.name == name
            ]

        return cb

    def sync(self) -> int:
        """Cria instrumentos para nomes ainda não registrados. Retorna nº de novos."""
        with self._lock:
            new = {m.name for m in self._agg.overview()} - self._known
            for name in sorted(new):
                self._meter.create_observable_gauge(
                    self._sanitize(name), callbacks=[self._callback_for(name)]
                )
                self._known.add(name)
            return len(new)


def init_metrics_export(agg: Any, settings: Any, reader: Any = None) -> MetricsExport | None:
    """Liga export OTLP de métricas se OTLP_METRICS_ENABLED=1.

    `reader` injetável para testes (InMemoryMetricReader). Retorna o
    MetricsExport ativo ou None (desligado/degradado).
    """
    if not getattr(settings, "otlp_metrics_enabled", False):
        return None
    try:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource

        from obs_svc.prometheus import _sanitize_name

        if reader is None:
            reader = PeriodicExportingMetricReader(
                OTLPMetricExporter(),
                export_interval_millis=float(settings.otlp_metrics_interval_s) * 1000.0,
            )
        resource = Resource.create(
            {"service.name": os.environ.get("OTEL_SERVICE_NAME", _SERVICE_NAME)}
        )
        provider = MeterProvider(resource=resource, metric_readers=[reader])
        meter = provider.get_meter("obs_svc")
        export = MetricsExport(agg, meter, _sanitize_name, provider)
        export.sync()
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
        logger.info(
            "OTLP metrics export ativo (endpoint=%s, intervalo=%ss)",
            endpoint,
            settings.otlp_metrics_interval_s,
        )
        return export
    except Exception as exc:  # noqa: BLE001 — degradação graceful (D7)
        logger.warning("OTLP metrics indisponivel (no-op): %s", exc)
        return None
