"""svc-orchestrator — API FastAPI. Swagger off; stack só em log."""

from __future__ import annotations

import json
import logging
import statistics
import time
import uuid
from collections import deque
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from orch_svc.clients import (
    HttpGuardrails,
    HttpInference,
    HttpRag,
    HttpRouter,
)
from orch_svc.config import VERSION, Settings, load_settings
from orch_svc.orchestrator import (
    Breakers,
    DownstreamUnavailable,
    Orchestrator,
    Thread,
    new_traceparent,
)
from orch_svc.schemas import (
    AgentResult,
    ChatRequest,
    ChatResponse,
    Health,
    Metrics,
    ResumeRequest,
    ThreadState,
)
from orch_svc.security import RateLimiter, client_ip, validate_outbound_url, verify_internal_key

logger = logging.getLogger("orch")


class State:
    def __init__(self, settings: Settings, orchestrator: Orchestrator | None = None) -> None:
        self.settings = settings
        self.rate_limiter = RateLimiter(settings.rate_limit_per_min)
        for url in (settings.guardrails_url, settings.router_url, settings.rag_url,
                    settings.inference_url):
            try:
                validate_outbound_url(url, settings.allow_local_downstream)
            except ValueError as exc:
                logger.warning("downstream URL suspeita %s: %s", url, exc)
        self.breakers = Breakers(settings.circuit_fail_threshold, settings.circuit_reset_s)
        self.orch = orchestrator or self._build_orch(settings)
        self.threads: dict[str, Thread] = {}
        self.chats_total = 0
        self.blocked_total = 0
        self.paused_total = 0
        self.by_domain: dict[str, int] = {}
        self.latencies: deque[float] = deque(maxlen=1000)

    def _build_orch(self, s: Settings) -> Orchestrator:
        g = HttpGuardrails(s.guardrails_url, s.downstream_key, s.model, s.downstream_timeout_s)
        r = HttpRouter(s.router_url, s.downstream_key, s.model, s.downstream_timeout_s)
        rag = (
            HttpRag(s.rag_url, s.downstream_key, s.model, s.downstream_timeout_s)
            if s.rag_enabled else None
        )
        inf = HttpInference(s.inference_url, s.downstream_key, s.model, s.downstream_timeout_s)
        return Orchestrator(g, r, rag, inf, self.breakers, hitl_enabled=s.hitl_enabled)

    def evict_threads(self) -> None:
        if len(self.threads) > self.settings.max_threads:
            for k in list(self.threads)[: len(self.threads) - self.settings.max_threads]:
                del self.threads[k]

    def account(self, thread: Thread) -> None:
        self.chats_total += 1
        if thread.decision == "blocked":
            self.blocked_total += 1
        elif thread.decision == "paused":
            self.paused_total += 1
        for d in thread.domains:
            self.by_domain[d] = self.by_domain.get(d, 0) + 1


def create_app(settings: Settings | None = None, state: State | None = None) -> FastAPI:
    settings = settings or load_settings()
    logging.basicConfig(level=settings.log_level)
    if settings.allow_open_access and not settings.internal_key:
        logger.warning("ALLOW_OPEN_ACCESS=1 sem INTERNAL_KEY — modo aberto (dev)")
    st = state or State(settings)

    app = FastAPI(title="svc-orchestrator", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.orch = st

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

    def _finish(thread: Thread) -> None:
        st.threads[thread.thread_id] = thread
        st.evict_threads()
        st.account(thread)

    def _response(thread: Thread) -> ChatResponse:
        return ChatResponse(
            thread_id=thread.thread_id, decision=thread.decision,  # type: ignore[arg-type]
            domains=thread.domains,
            agents=[AgentResult(**a) for a in thread.agents],
            final=thread.final, pending_write=thread.pending_write,
        )

    def _sse(events: Any, thread: Thread, trace: str) -> StreamingResponse:
        def gen() -> Any:
            try:
                for ev in events:
                    yield f"event: {ev.type}\ndata: {json.dumps(ev.data)}\n\n"
                _finish(thread)
            except DownstreamUnavailable as exc:
                yield f'event: error\ndata: {json.dumps({"service": exc.service})}\n\n'
            yield "event: done\ndata: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/v1/chat")
    def chat(req: ChatRequest, request: Request, _: None = Depends(auth)) -> Any:
        start = time.perf_counter()
        trace = request.headers.get("traceparent") or new_traceparent()
        thread = Thread(thread_id=req.thread_id or f"th-{uuid.uuid4().hex[:16]}", query=req.query)

        if req.stream:
            events = st.orch.run(thread, trace, allow_write=req.allow_write)
            return _sse(events, thread, trace)

        try:
            list(st.orch.run(thread, trace, allow_write=req.allow_write))
        except DownstreamUnavailable as exc:
            msg = f"downstream {exc.service} indisponivel"
            raise HTTPException(status_code=503, detail=msg) from exc
        _finish(thread)
        st.latencies.append((time.perf_counter() - start) * 1000.0)
        if thread.decision == "blocked":
            return JSONResponse(status_code=403, content=_response(thread).model_dump())
        return _response(thread)

    @app.post("/v1/chat/{thread_id}/resume", response_model=ChatResponse)
    def resume(
        thread_id: str, req: ResumeRequest, request: Request,
        _: None = Depends(auth),
    ) -> Any:
        thread = st.threads.get(thread_id)
        if thread is None or thread.decision != "paused":
            raise HTTPException(status_code=404, detail="thread sem pausa pendente")
        trace = request.headers.get("traceparent") or new_traceparent()
        try:
            list(st.orch.resume(thread, trace, approve=req.approve))
        except DownstreamUnavailable as exc:
            msg = f"downstream {exc.service} indisponivel"
            raise HTTPException(status_code=503, detail=msg) from exc
        st.threads[thread_id] = thread
        return _response(thread)

    @app.get("/v1/threads/{thread_id}", response_model=ThreadState)
    def thread_state(thread_id: str, _: None = Depends(auth)) -> ThreadState:
        thread = st.threads.get(thread_id)
        if thread is None:
            raise HTTPException(status_code=404, detail="thread inexistente")
        return ThreadState(thread_id=thread.thread_id, decision=thread.decision,  # type: ignore[arg-type]
                           final=thread.final, pending_write=thread.pending_write)

    @app.get("/health", response_model=Health)
    def health() -> Health:
        deps = {
            "guardrails": st.breakers.guardrails.state.value,
            "router": st.breakers.router.state.value,
            "rag": st.breakers.rag.state.value,
            "inference": st.breakers.inference.state.value,
        }
        degraded = any(v == "open" for v in deps.values())
        return Health(status="degraded" if degraded else "ok", version=VERSION, deps=deps)

    @app.get("/metrics", response_model=Metrics)
    def metrics(_: None = Depends(auth)) -> Metrics:
        lat = sorted(st.latencies)
        p50 = statistics.median(lat) if lat else 0.0
        p95 = lat[max(0, int(len(lat) * 0.95) - 1)] if lat else 0.0
        return Metrics(
            chats_total=st.chats_total, blocked_total=st.blocked_total,
            paused_total=st.paused_total, by_domain=dict(st.by_domain),
            latency_ms_p50=round(p50, 2), latency_ms_p95=round(p95, 2),
        )

    return app


app = create_app()

__all__ = ["create_app", "State"]
