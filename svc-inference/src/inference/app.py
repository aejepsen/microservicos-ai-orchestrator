"""svc-inference — fachada FastAPI OpenAI-compatível. Swagger off; stack só em log."""

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

from inference import otel
from inference.backends import Backend, build_backend
from inference.circuit import BackendBusiness, BackendError, CircuitBreaker, CircuitOpen
from inference.config import VERSION, Settings, load_settings
from inference.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    Health,
    Metrics,
    Usage,
)
from inference.security import RateLimiter, client_ip, verify_internal_key

logger = logging.getLogger("inference")


class State:
    def __init__(self, settings: Settings, backend: Backend | None = None) -> None:
        self.settings = settings
        self.rate_limiter = RateLimiter(settings.rate_limit_per_min)
        self.breaker = CircuitBreaker(settings.circuit_fail_threshold, settings.circuit_reset_s)
        self.backend = backend or build_backend(settings)
        self.requests_total = 0
        self.tokens_input_total = 0
        self.tokens_output_total = 0
        self.ttft: deque[float] = deque(maxlen=1000)
        self.latencies: deque[float] = deque(maxlen=1000)
        otel.init(settings)


def _messages(req: ChatCompletionRequest) -> list[dict[str, str]]:
    return [{"role": m.role, "content": m.content} for m in req.messages]


def create_app(settings: Settings | None = None, state: State | None = None) -> FastAPI:
    settings = settings or load_settings()
    logging.basicConfig(level=settings.log_level)
    if settings.allow_open_access and not settings.internal_key:
        logger.warning("ALLOW_OPEN_ACCESS=1 sem INTERNAL_KEY — modo aberto (dev)")
    st = state or State(settings)

    app = FastAPI(title="svc-inference", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.inference = st

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

    def _record(model: str, usage: Usage, duration_s: float, ttft_s: float | None) -> None:
        st.requests_total += 1
        st.tokens_input_total += usage.prompt_tokens
        st.tokens_output_total += usage.completion_tokens
        st.latencies.append(duration_s * 1000.0)
        if ttft_s is not None:
            st.ttft.append(ttft_s * 1000.0)
        otel.record_llm_call(
            model=model, duration_s=duration_s,
            input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens, ttft_s=ttft_s,
        )

    def _handle_backend_error(exc: Exception) -> HTTPException:
        if isinstance(exc, CircuitOpen):
            return HTTPException(status_code=503, detail="circuito OPEN")
        if isinstance(exc, BackendBusiness):
            return HTTPException(status_code=503, detail=f"backend erro {exc.status}")
        return HTTPException(status_code=503, detail="backend indisponivel")

    @app.post("/v1/chat/completions")
    def chat_completions(
        req: ChatCompletionRequest, request: Request, _: None = Depends(auth)
    ) -> Any:
        model = req.model or st.settings.default_model
        if not model:
            return JSONResponse(
                status_code=422,
                content={
                    "error": "model_ausente",
                    "detail": "campo 'model' obrigatorio",
                    "rule": "chat",
                },
            )
        messages = _messages(req)

        if req.stream:
            return _stream_response(st, model, messages, _record)

        # Bloqueante.
        try:
            st.breaker.before_call()
            start = time.perf_counter()
            completion = st.backend.chat(model, messages, temperature=req.temperature)
            duration = time.perf_counter() - start
            st.breaker.on_success()
        except BackendBusiness as exc:
            raise _handle_backend_error(exc) from exc  # 4xx não abre circuito
        except (BackendError, CircuitOpen) as exc:
            if isinstance(exc, BackendError):
                st.breaker.on_transport_failure()
            raise _handle_backend_error(exc) from exc

        usage = Usage(**completion.usage.__dict__)
        _record(model, usage, duration, None)
        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:24]}", model=model,
            choices=[Choice(
                index=0,
                message=ChatMessage(role="assistant", content=completion.content),
                finish_reason=completion.finish_reason,
            )],
            usage=usage,
        )

    @app.get("/v1/models")
    def list_models(_: None = Depends(auth)) -> Any:
        try:
            st.breaker.before_call()
            models = st.backend.list_models()
            st.breaker.on_success()
        except (BackendError, CircuitOpen) as exc:
            if isinstance(exc, BackendError):
                st.breaker.on_transport_failure()
            raise _handle_backend_error(exc) from exc
        return {"object": "list", "data": [{"id": m, "object": "model"} for m in models]}

    @app.get("/health", response_model=Health)
    def health() -> Health:
        state_val = st.breaker.state.value
        backend_ok = state_val != "open"
        deps = {"backend": "ok" if backend_ok else "down", "circuit": state_val}
        status = "ok" if backend_ok else "degraded"
        return Health(status=status, version=VERSION, deps=deps)  # type: ignore[arg-type]

    @app.get("/metrics", response_model=Metrics)
    def metrics(_: None = Depends(auth)) -> Metrics:
        def _p(seq: deque[float], q: float) -> float:
            s = sorted(seq)
            return s[max(0, int(len(s) * q) - 1)] if s else 0.0

        lat = sorted(st.latencies)
        return Metrics(
            requests_total=st.requests_total,
            tokens_input_total=st.tokens_input_total,
            tokens_output_total=st.tokens_output_total,
            ttft_ms_p50=round(_p(st.ttft, 0.50), 2), ttft_ms_p95=round(_p(st.ttft, 0.95), 2),
            latency_ms_p50=round(statistics.median(lat) if lat else 0.0, 2),
            latency_ms_p95=round(_p(st.latencies, 0.95), 2),
            circuit_state=st.breaker.state.value,
        )

    otel.init_tracing(app, settings)
    return app


def _stream_response(st: State, model: str, messages: list[dict[str, str]], record: Any) -> Any:
    def gen() -> Any:
        cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        start = time.perf_counter()
        ttft: float | None = None
        try:
            st.breaker.before_call()
            stream = st.backend.chat_stream(model, messages)
            for i, chunk in enumerate(stream):
                if i == 0:
                    ttft = time.perf_counter() - start
                data: dict[str, Any] = {
                    "id": cid, "object": "chat.completion.chunk", "model": model,
                    "choices": [{"index": 0, "delta": {"content": chunk.delta},
                                 "finish_reason": chunk.finish_reason}],
                }
                if chunk.usage is not None:
                    u = chunk.usage
                    data["usage"] = {"prompt_tokens": u.prompt_tokens,
                                     "completion_tokens": u.completion_tokens,
                                     "total_tokens": u.total_tokens}
                    record(model, Usage(**u.__dict__), time.perf_counter() - start, ttft)
                yield f"data: {json.dumps(data)}\n\n"
            st.breaker.on_success()
            yield "data: [DONE]\n\n"
        except BackendBusiness:
            yield f'data: {json.dumps({"error": "backend erro de negocio"})}\n\n'
        except (BackendError, CircuitOpen) as exc:
            if isinstance(exc, BackendError):
                st.breaker.on_transport_failure()
            yield f'data: {json.dumps({"error": "backend indisponivel"})}\n\n'

    return StreamingResponse(gen(), media_type="text/event-stream")


app = create_app()
