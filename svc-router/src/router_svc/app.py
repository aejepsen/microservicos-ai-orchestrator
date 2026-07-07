"""svc-router — API FastAPI. Swagger off; stack só em log."""

from __future__ import annotations

import logging
import statistics
import time
from collections import deque
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from router_svc import otel
from router_svc.config import VERSION, Settings, load_settings
from router_svc.embedder import FakeEmbedder, SbertEmbedder
from router_svc.guards import apply_guards, guards
from router_svc.llm import FakeLLM, HttpLLM, LLMClassifier
from router_svc.router import LLMUnavailable, Router
from router_svc.routes import registry
from router_svc.schemas import Health, Metrics, RouteInfo, RoutePlan, RouteRequest
from router_svc.security import (
    RateLimiter,
    client_ip,
    validate_outbound_url,
    verify_internal_key,
)

logger = logging.getLogger("router")


def _count_guards_for(domain: str) -> int:
    return sum(1 for g in guards() if domain in g.domains)


class State:
    def __init__(self, settings: Settings, embedder: Any = "auto", llm: Any = "auto") -> None:
        self.settings = settings
        self.rate_limiter = RateLimiter(settings.rate_limit_per_min)
        self.embedder = self._build_embedder(settings) if embedder == "auto" else embedder
        self.llm: LLMClassifier | None = self._build_llm(settings) if llm == "auto" else llm
        base_routes = [(r.name, r.exemplars) for r in registry()]
        self.router = Router(
            base_routes, self.embedder,
            threshold=settings.route_threshold, tie_margin=settings.tie_margin,
            rrf_k=settings.rrf_k, hybrid=settings.hybrid_enabled,
        )
        self.routes_total = 0
        self.by_layer: dict[str, int] = {"semantic": 0, "lexical": 0, "llm": 0, "fallback": 0}
        self.latencies: deque[float] = deque(maxlen=1000)

    @staticmethod
    def _build_embedder(settings: Settings) -> Any:
        try:
            return SbertEmbedder(settings.embed_model)
        except Exception as exc:  # noqa: BLE001 — degradação declarada
            logger.warning("embedder indisponivel (semantica off): %s", exc)
            return None

    @staticmethod
    def _build_llm(settings: Settings) -> LLMClassifier | None:
        if settings.llm_enabled and settings.llm_url:
            try:
                validate_outbound_url(settings.llm_url, settings.allow_local_llm)
            except ValueError as exc:
                logger.error("LLM_URL invalida (camada LLM desativada): %s", exc)
                return None
            return HttpLLM(settings.llm_url, settings.llm_model)
        return None


def create_app(settings: Settings | None = None, state: State | None = None) -> FastAPI:
    settings = settings or load_settings()
    logging.basicConfig(level=settings.log_level)
    if settings.allow_open_access and not settings.internal_key:
        logger.warning("ALLOW_OPEN_ACCESS=1 sem INTERNAL_KEY — modo aberto (dev)")
    st = state or State(settings)

    app = FastAPI(title="svc-router", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.router = st

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

    @app.post("/v1/route", response_model=RoutePlan)
    def route(req: RouteRequest, request: Request, _: None = Depends(auth)) -> Any:
        if len(req.query) > st.settings.max_query_chars:
            return JSONResponse(
                status_code=422,
                content={
                    "error": "query_longa",
                    "detail": "excede MAX_QUERY_CHARS",
                    "rule": "route",
                },
            )
        active_router = st.router
        if req.routes_override:
            active_router = Router(
                [(r.name, r.exemplars) for r in req.routes_override], st.embedder,
                threshold=st.settings.route_threshold, tie_margin=st.settings.tie_margin,
                rrf_k=st.settings.rrf_k, hybrid=st.settings.hybrid_enabled,
            )

        start = time.perf_counter()
        try:
            plan = active_router.route(
                req.query, allow_llm=req.allow_llm, llm=st.llm,
                soft_fallback=st.settings.llm_fallback_soft,
            )
        except LLMUnavailable as exc:
            raise HTTPException(status_code=503, detail="camada LLM indisponivel") from exc

        latency_ms = (time.perf_counter() - start) * 1000.0
        st.routes_total += 1
        st.by_layer[plan.layer] = st.by_layer.get(plan.layer, 0) + 1
        st.latencies.append(latency_ms)
        logger.info(
            '{"event":"route","layer":%r,"domains":%s,"llm_used":%s,"latency_ms":%.1f}',
            plan.layer, plan.domains, plan.llm_used, latency_ms,
        )
        return RoutePlan(**plan.__dict__)

    @app.get("/v1/routes", response_model=list[RouteInfo])
    def list_routes(_: None = Depends(auth)) -> list[RouteInfo]:
        return [
            RouteInfo(name=r.name, n_exemplars=len(r.exemplars), n_guards=_count_guards_for(r.name))
            for r in registry()
        ]

    @app.get("/health", response_model=Health)
    def health() -> Health:
        deps = {
            "embedder": "ok" if st.embedder is not None else "down",
            "llm_adapter": "enabled" if st.llm is not None else "disabled",
        }
        status = "ok" if deps["embedder"] == "ok" else "degraded"
        return Health(status=status, version=VERSION, deps=deps)  # type: ignore[arg-type]

    @app.get("/metrics", response_model=Metrics)
    def metrics(_: None = Depends(auth)) -> Metrics:
        lat = sorted(st.latencies)
        p50 = statistics.median(lat) if lat else 0.0
        p95 = lat[max(0, int(len(lat) * 0.95) - 1)] if lat else 0.0
        return Metrics(
            routes_total=st.routes_total, by_layer=dict(st.by_layer),
            latency_ms_p50=round(p50, 2), latency_ms_p95=round(p95, 2),
        )

    otel.init_tracing(app, settings)
    return app


app = create_app()


# Reexport para testes/evals construírem estado offline.
__all__ = ["create_app", "State", "FakeEmbedder", "FakeLLM", "apply_guards"]
