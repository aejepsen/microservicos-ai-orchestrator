"""svc-observability — API FastAPI. Swagger off; stack só em log."""

from __future__ import annotations

import logging
import statistics
import time
from collections import deque
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from obs_svc import otel
from obs_svc.aggregator import Aggregator
from obs_svc.config import VERSION, Settings, load_settings
from obs_svc.prometheus import render
from obs_svc.schemas import (
    EvalResultIn,
    EvalResultResponse,
    Health,
    MetricModel,
    Metrics,
    Overview,
    RefreshResponse,
    ServiceStatus,
)
from obs_svc.scraper import FakeScraper, HttpScraper, Scraper
from obs_svc.security import RateLimiter, client_ip, validate_outbound_url, verify_internal_key
from obs_svc.security_headers import add_security_headers
from obs_svc.upstreams import registry

logger = logging.getLogger("obs")


class State:
    def __init__(self, settings: Settings, scraper: Any = "auto") -> None:
        self.settings = settings
        self.rate_limiter = RateLimiter(settings.rate_limit_per_min)
        ups = registry()
        # Anti-SSRF: valida URLs de upstream no boot (salvo allow_local).
        for u in ups:
            try:
                validate_outbound_url(u.url, settings.allow_local_upstream)
            except ValueError as exc:
                logger.warning("upstream %s URL suspeita: %s", u.name, exc)
        self.scraper: Scraper = self._build_scraper(settings) if scraper == "auto" else scraper
        self.agg = Aggregator(ups, self.scraper)
        self.overviews_total = 0
        self.latencies: deque[float] = deque(maxlen=1000)

    @staticmethod
    def _build_scraper(settings: Settings) -> Scraper:
        return HttpScraper(settings.upstream_key, settings.scrape_timeout_s)


def _to_model(m: Any) -> MetricModel:
    return MetricModel(
        name=m.name, value=m.value, source=str(m.source), service=m.service,  # type: ignore[arg-type]
        unit=m.unit, ts=m.ts, stale=m.stale,
    )


def create_app(settings: Settings | None = None, state: State | None = None) -> FastAPI:
    settings = settings or load_settings()
    logging.basicConfig(level=settings.log_level)
    if settings.allow_open_access and not settings.internal_key:
        logger.warning("ALLOW_OPEN_ACCESS=1 sem INTERNAL_KEY — modo aberto (dev)")
    st = state or State(settings)

    app = FastAPI(title="svc-observability", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.obs = st

    def auth(request: Request) -> None:
        verify_internal_key(request, st.settings)

    @app.middleware("http")
    async def rate_limit_mw(request: Request, call_next: Any) -> Any:
        if request.url.path.startswith("/v1/") and not st.rate_limiter.allow(client_ip(request)):
            return JSONResponse(status_code=429, content={"detail": "rate limit excedido"})
        return await call_next(request)

    @app.exception_handler(Exception)
    async def internal_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("erro interno: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "Erro interno. Tente novamente."})

    @app.get("/v1/overview", response_model=Overview)
    def overview(_: None = Depends(auth)) -> Overview:
        start = time.perf_counter()
        metrics = [_to_model(m) for m in st.agg.overview()]
        st.overviews_total += 1
        st.latencies.append((time.perf_counter() - start) * 1000.0)
        return Overview(generated_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"), metrics=metrics)

    @app.get("/v1/services", response_model=list[ServiceStatus])
    def services(_: None = Depends(auth)) -> list[ServiceStatus]:
        return [
            ServiceStatus(name=s.name, url=s.url, last_scrape=s.last_scrape,
                          ok=s.ok, n_metrics=len(s.metrics))
            for s in st.agg.services()
        ]

    @app.post("/v1/refresh", response_model=RefreshResponse)
    def refresh(_: None = Depends(auth)) -> RefreshResponse:
        ok, failed = st.agg.refresh()
        return RefreshResponse(scraped=ok + failed, ok=ok, failed=failed)

    @app.post("/v1/eval-results", response_model=EvalResultResponse)
    def ingest_eval(req: EvalResultIn, _: None = Depends(auth)) -> EvalResultResponse:
        n = st.agg.ingest_eval(req.service, req.dataset_date, [m.model_dump() for m in req.metrics])
        return EvalResultResponse(ingested=n)

    @app.get("/v1/prometheus")
    def prometheus(_: None = Depends(auth)) -> PlainTextResponse:
        return PlainTextResponse(render(st.agg.overview()))

    @app.get("/health", response_model=Health)
    def health() -> Health:
        up = st.agg.upstreams_up()
        total = len(st.agg.services())
        status = "ok" if up == total else "degraded"
        return Health(
            status=status, version=VERSION,  # type: ignore[arg-type]
            deps={"upstreams_up": up, "upstreams_total": total},
        )

    @app.get("/metrics", response_model=Metrics)
    def metrics(_: None = Depends(auth)) -> Metrics:
        lat = sorted(st.latencies)
        p50 = statistics.median(lat) if lat else 0.0
        p95 = lat[max(0, int(len(lat) * 0.95) - 1)] if lat else 0.0
        return Metrics(
            scrapes_total=st.agg.scrapes_total, overviews_total=st.overviews_total,
            upstreams_up=st.agg.upstreams_up(),
            latency_ms_p50=round(p50, 2), latency_ms_p95=round(p95, 2),
        )

    add_security_headers(app)
    otel.init_tracing(app, settings)
    return app


app = create_app()

__all__ = ["create_app", "State", "FakeScraper"]
