"""svc-guardrails — API FastAPI.

Swagger/OpenAPI desabilitados (docs_url=None): o contrato vive em
api/openapi.yaml, versionado no repo. Stack traces nunca saem na resposta.
"""

from __future__ import annotations

import logging
import statistics
import threading
import time
from collections import deque
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from guardrails.config import VERSION, Settings, load_settings
from guardrails.injection import detect_injection
from guardrails.ood import OodGuard, SbertEmbedder
from guardrails.sanitize import sanitize
from guardrails.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    Health,
    InjectionVerdictModel,
    Metrics,
    OodFitRequest,
    OodFitResponse,
    OodStatus,
    OodVerdictModel,
    Verdicts,
)
from guardrails.security import RateLimiter, client_ip, verify_internal_key

logger = logging.getLogger("guardrails")


class State:
    """Estado de processo: embedder, guard OOD, contadores (source=live)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.rate_limiter = RateLimiter(settings.rate_limit_per_min)
        self.ood_guard = OodGuard(settings.models_dir)
        self.fit_lock = threading.Lock()
        self.embedder: Any = None
        self.analyses_total = 0
        self.blocks_total = 0
        self.flags_total = 0
        self.latencies: deque[float] = deque(maxlen=1000)
        try:
            # Carregado no boot — lazy loading proibido (cold start no 1º request).
            self.embedder = SbertEmbedder(settings.embed_model)
        except Exception as exc:  # noqa: BLE001 — degradação declarada, não crash
            logger.warning("embedder indisponivel (checks ood degradados): %s", exc)


def create_app(settings: Settings | None = None, state: State | None = None) -> FastAPI:
    settings = settings or load_settings()
    logging.basicConfig(level=settings.log_level)
    if settings.allow_open_access and not settings.internal_key:
        logger.warning("ALLOW_OPEN_ACCESS=1 sem INTERNAL_KEY — modo aberto (somente dev)")
    st = state or State(settings)

    app = FastAPI(title="svc-guardrails", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.guardrails = st

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

    @app.post("/v1/analyze", response_model=AnalyzeResponse)
    def analyze(req: AnalyzeRequest, request: Request, _: None = Depends(auth)) -> AnalyzeResponse:
        start = time.perf_counter()
        if len(req.text) > st.settings.max_text_chars:
            raise HTTPException(status_code=413, detail="texto excede MAX_TEXT_CHARS")

        sanitized, _actions = sanitize(req.text) if "sanitize" in req.checks else (req.text, [])

        inj_model: InjectionVerdictModel | None = None
        if "injection" in req.checks:
            # Sobre o texto ORIGINAL: delimitadores neutralizados seguem sendo evidência.
            verdict = detect_injection(req.text)
            inj_model = InjectionVerdictModel(
                flagged=verdict.flagged, score=verdict.score, patterns=verdict.patterns
            )

        ood_model: OodVerdictModel | None = None
        if "ood" in req.checks:
            if st.ood_guard.fitted and st.embedder is not None:
                v = st.ood_guard.check(sanitized, st.embedder)
                ood_model = OodVerdictModel(
                    flagged=v.flagged, residual=v.residual, threshold=v.threshold
                )
            elif st.settings.ood_required:
                raise HTTPException(status_code=503, detail="OOD exigido sem artefato fitado")

        if inj_model and inj_model.flagged:
            decision = "block"  # inegociável (spec §5.3)
        elif ood_model and ood_model.flagged:
            decision = "block" if st.settings.ood_action == "block" else "flag"
        else:
            decision = "allow"

        latency_ms = (time.perf_counter() - start) * 1000.0
        st.analyses_total += 1
        st.latencies.append(latency_ms)
        if decision == "block":
            st.blocks_total += 1
        elif decision == "flag":
            st.flags_total += 1

        preview = req.text[:80].replace("\n", "\\n") if st.settings.log_text_preview else ""
        logger.info(
            '{"event":"analyze","context":%r,"decision":%r,"patterns":%s,'
            '"ood_residual":%s,"latency_ms":%.1f,"preview":%r}',
            req.context or "",
            decision,
            inj_model.patterns if inj_model else [],
            ood_model.residual if ood_model else None,
            latency_ms,
            preview,
        )
        return AnalyzeResponse(
            sanitized_text=sanitized,
            verdicts=Verdicts(injection=inj_model, ood=ood_model),
            decision=decision,  # type: ignore[arg-type]
            latency_ms=round(latency_ms, 2),
        )

    @app.post("/v1/ood/fit", response_model=OodFitResponse)
    def ood_fit(req: OodFitRequest, _: None = Depends(auth)) -> OodFitResponse:
        if st.embedder is None:
            return JSONResponse(  # type: ignore[return-value]
                status_code=422,
                content={
                    "error": "embedder_indisponivel",
                    "detail": "embedder nao carregado",
                    "rule": "ood_fit",
                },
            )
        if not st.fit_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="fit em andamento")
        try:
            report = st.ood_guard.fit(
                [s.model_dump() for s in req.in_domain], req.ood_calibration, st.embedder
            )
        except ValueError as exc:
            return JSONResponse(  # type: ignore[return-value]
                status_code=422,
                content={"error": "corpus_insuficiente", "detail": str(exc), "rule": "ood_fit"},
            )
        finally:
            st.fit_lock.release()
        return OodFitResponse(**report.__dict__)

    @app.get("/v1/ood/status", response_model=OodStatus)
    def ood_status(_: None = Depends(auth)) -> OodStatus:
        if not st.ood_guard.fitted:
            return OodStatus(fitted=False)
        meta = st.ood_guard.meta
        return OodStatus(
            fitted=True,
            n_samples=int(meta.get("n_samples", 0)),
            threshold=float(meta.get("threshold", 0.0)),
            auc_loo=float(meta.get("auc_loo", 0.0)),
            fitted_at=str(meta.get("fitted_at", "")),
            corpus_hash=str(meta.get("corpus_hash", "")),
        )

    @app.get("/health", response_model=Health)
    def health() -> Health:
        deps = {
            "embedder": "ok" if st.embedder is not None else "down",
            "ood_artifact": "ok" if st.ood_guard.fitted else "absent",
        }
        status = "ok" if deps["embedder"] == "ok" else "degraded"
        return Health(status=status, version=VERSION, deps=deps)  # type: ignore[arg-type]

    @app.get("/metrics", response_model=Metrics)
    def metrics(_: None = Depends(auth)) -> Metrics:
        lat = sorted(st.latencies)
        p50 = statistics.median(lat) if lat else 0.0
        p95 = lat[max(0, int(len(lat) * 0.95) - 1)] if lat else 0.0
        return Metrics(
            analyses_total=st.analyses_total,
            blocks_total=st.blocks_total,
            flags_total=st.flags_total,
            latency_ms_p50=round(p50, 2),
            latency_ms_p95=round(p95, 2),
        )

    return app


app = create_app()
