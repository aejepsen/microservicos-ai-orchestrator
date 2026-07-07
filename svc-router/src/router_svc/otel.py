"""DS-01 — OTel real: spans OTLP (FastAPI server + httpx client).

OTEL_ENABLED=0 (default): no-op absoluto — gates offline intactos (G-OTEL-1).
OTEL_ENABLED=1: TracerProvider + exporter OTLP HTTP; auto-instrumentação
FastAPI e httpx; trace IDs consistentes com o traceparent W3C já propagado.
Degradação graceful: SDK ausente ou collector fora → warning, nunca falha.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("router")

_SERVICE_NAME = "svc-router"


def init_tracing(app: Any, settings: Any) -> bool:
    """Liga traces OTLP se OTEL_ENABLED=1. Retorna True se ativo."""
    if not getattr(settings, "otel_enabled", False):
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

        ratio = float(os.environ.get("OTEL_TRACES_SAMPLER_ARG", "1.0"))
        resource = Resource.create(
            {"service.name": os.environ.get("OTEL_SERVICE_NAME", _SERVICE_NAME)}
        )
        provider = TracerProvider(
            resource=resource, sampler=ParentBased(TraceIdRatioBased(ratio))
        )
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")
        HTTPXClientInstrumentor().instrument()
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
        logger.info("OTel traces ativo (endpoint=%s)", endpoint)
        return True
    except Exception as exc:  # noqa: BLE001 — degradação graceful (DS-01)
        logger.warning("OTel indisponivel (no-op): %s", exc)
        return False
