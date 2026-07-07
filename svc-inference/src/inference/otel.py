"""OTel GenAI semconv (padrão AI-Orchestrator gateway/otel.py).

Instrumentação manual: span por chamada LLM + histogramas token.usage,
operation.duration e time_to_first_token. Degradação graceful: OTEL_ENABLED=0,
SDK ausente ou Collector fora → record vira no-op; request nunca falha.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("inference")

_enabled = False
_token_hist: Any = None
_duration_hist: Any = None
_ttft_hist: Any = None
_GEN_AI_SYSTEM = "ollama"


def init(settings: Any) -> bool:
    global _enabled, _token_hist, _duration_hist, _ttft_hist
    if not getattr(settings, "otel_enabled", False):
        return False
    try:
        from opentelemetry import metrics
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        reader = PeriodicExportingMetricReader(OTLPMetricExporter())
        metrics.set_meter_provider(MeterProvider(metric_readers=[reader]))
        meter = metrics.get_meter("inference.genai")
        _token_hist = meter.create_histogram("gen_ai.client.token.usage", unit="{token}")
        _duration_hist = meter.create_histogram("gen_ai.client.operation.duration", unit="s")
        _ttft_hist = meter.create_histogram("gen_ai.server.time_to_first_token", unit="s")
        _enabled = True
        logger.info("OTel GenAI ativo")
        return True
    except Exception as exc:  # noqa: BLE001 — degradação graceful
        logger.warning("OTel indisponivel (no-op): %s", exc)
        _enabled = False
        return False


def record_llm_call(
    *, model: str, duration_s: float, input_tokens: int, output_tokens: int, ttft_s: float | None
) -> None:
    """No-op se OTel desligado. Nunca lança."""
    if not _enabled:
        return
    try:
        attrs = {"gen_ai.system": _GEN_AI_SYSTEM, "gen_ai.request.model": model}
        _token_hist.record(input_tokens, {**attrs, "gen_ai.token.type": "input"})
        _token_hist.record(output_tokens, {**attrs, "gen_ai.token.type": "output"})
        _duration_hist.record(duration_s, attrs)
        if ttft_s is not None:
            _ttft_hist.record(ttft_s, attrs)
    except Exception as exc:  # noqa: BLE001
        logger.debug("OTel record falhou (ignorado): %s", exc)


def init_tracing(app: Any, settings: Any) -> bool:
    """DS-01 — spans OTLP (FastAPI server + httpx client). No-op se OTEL_ENABLED=0."""
    if not getattr(settings, "otel_enabled", False):
        return False
    try:
        import os

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
            {"service.name": os.environ.get("OTEL_SERVICE_NAME", "svc-inference")}
        )
        provider = TracerProvider(
            resource=resource, sampler=ParentBased(TraceIdRatioBased(ratio))
        )
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")
        HTTPXClientInstrumentor().instrument()
        logger.info("OTel traces ativo")
        return True
    except Exception as exc:  # noqa: BLE001 — degradação graceful (DS-01)
        logger.warning("OTel traces indisponivel (no-op): %s", exc)
        return False
