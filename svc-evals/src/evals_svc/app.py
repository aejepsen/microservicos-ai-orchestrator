"""svc-evals — API FastAPI. Swagger off; stack traces nunca saem na resposta."""

from __future__ import annotations

import json
import logging
import statistics
import time
from collections import deque
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from evals_svc import otel
from evals_svc.config import VERSION, Settings, load_settings
from evals_svc.judge import HttpJudge, score_llm_judge
from evals_svc.results_store import ResultsStore
from evals_svc.runner import live_response_fn, run_suite
from evals_svc.schemas import (
    GateSpec,
    Health,
    Metrics,
    ResultsAggregate,
    RunRequest,
    RunResponse,
    SuiteInfo,
)
from evals_svc.scorers import SCORERS
from evals_svc.security import (
    RateLimiter,
    client_ip,
    validate_outbound_url,
    verify_internal_key,
)
from evals_svc.security_headers import add_security_headers
from evals_svc.suites import get_suite, list_suites

logger = logging.getLogger("evals")

DATA = Path(__file__).resolve().parents[2] / "evals" / "data"


class State:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.rate_limiter = RateLimiter(settings.rate_limit_per_min)
        self.store = ResultsStore(settings.results_dir, settings.results_cache_ttl_s)
        self.judge: Any = None
        if settings.judge_enabled and settings.judge_url:
            self.judge = HttpJudge(
                settings.judge_url, settings.judge_model, settings.judge_timeout_s
            )
        self.runs_total = 0
        self.gates_pass_total = 0
        self.gates_fail_total = 0
        self.latencies: deque[float] = deque(maxlen=1000)


def _load_golden(name: str) -> list[dict[str, Any]]:
    path = DATA / name
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def create_app(settings: Settings | None = None, state: State | None = None) -> FastAPI:
    settings = settings or load_settings()
    logging.basicConfig(level=settings.log_level)
    if settings.allow_open_access and not settings.internal_key:
        logger.warning("ALLOW_OPEN_ACCESS=1 sem INTERNAL_KEY — modo aberto (dev)")
    st = state or State(settings)

    app = FastAPI(title="svc-evals", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.evals = st

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

    def _err(status: int, error: str, detail: str, rule: str) -> JSONResponse:
        return JSONResponse(
            status_code=status, content={"error": error, "detail": detail, "rule": rule}
        )

    @app.post("/v1/run", response_model=RunResponse)
    def run(req: RunRequest, request: Request, _: None = Depends(auth)) -> Any:
        start = time.perf_counter()

        # Resolve golden + scorer + gate: suite registrada OU definição inline.
        if req.suite and get_suite(req.suite):
            suite = get_suite(req.suite)
            assert suite is not None
            cases = _load_golden(suite.golden)
            scorer_name = suite.scorer
            scorer_params = dict(suite.scorer_params)
            gate = {"metric": suite.metric, **suite.gate} if suite.gate else None
            suite_name = suite.name
            source = suite.source
        elif req.golden_inline is not None and req.scorer:
            cases = req.golden_inline
            scorer_name = req.scorer
            scorer_params = dict(req.scorer_params)
            gate = req.gate.model_dump() if req.gate else None
            suite_name = req.suite or "inline"
            source = req.source
        else:
            return _err(
                422, "suite_invalida",
                "informe 'suite' registrada ou 'golden_inline'+'scorer'", "run",
            )

        if scorer_name not in SCORERS and scorer_name != "llm_judge":
            return _err(422, "scorer_invalido", f"scorer desconhecido: {scorer_name}", "run")

        # llm_judge exige adapter ligado.
        if scorer_name == "llm_judge":
            if st.judge is None:
                raise HTTPException(status_code=503, detail="llm_judge exige JUDGE_ENABLED=1")
            scorer_params["_judge"] = st.judge
            SCORERS["llm_judge"] = score_llm_judge

        # Modo live: valida SSRF e monta response_fn.
        response_fn = None
        if req.mode == "live":
            if req.target is None:
                return _err(422, "target_ausente", "mode=live exige 'target'", "run")
            validate_outbound_url(req.target.url, st.settings.allow_local_target)
            try:
                response_fn = live_response_fn(
                    req.target.model_dump(), st.settings.target_deadline_s
                )
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=424, detail=f"alvo indisponivel: {exc}") from exc

        try:
            outcome = (
                run_suite(cases, scorer_name, scorer_params, gate, response_fn)
                if response_fn
                else run_suite(cases, scorer_name, scorer_params, gate)
            )
        except ValueError as exc:
            return _err(422, "golden_invalido", str(exc), "run")
        except Exception as exc:  # noqa: BLE001 — alvo/juiz fora vira 424
            raise HTTPException(status_code=424, detail=f"falha ao obter respostas: {exc}") from exc

        ran_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        payload = {
            "suite": suite_name, "metric": outcome.metric, "value": outcome.value,
            "gate": gate, "passed": outcome.passed, "n_cases": outcome.n_cases,
            "n_failed_cases": outcome.n_failed_cases, "source": source, "ran_at": ran_at,
            "per_case": outcome.per_case,
        }
        artifact = st.store.write(suite_name, payload)

        st.runs_total += 1
        if outcome.passed is True:
            st.gates_pass_total += 1
        elif outcome.passed is False:
            st.gates_fail_total += 1
        latency_ms = (time.perf_counter() - start) * 1000.0
        st.latencies.append(latency_ms)
        logger.info(
            '{"event":"run","suite":%r,"metric":%r,"value":%s,"passed":%s,'
            '"n":%d,"source":%r,"latency_ms":%.1f}',
            suite_name, outcome.metric, outcome.value, outcome.passed,
            outcome.n_cases, source, latency_ms,
        )
        return RunResponse(
            suite=suite_name, metric=outcome.metric, value=outcome.value,
            gate=GateSpec(**gate) if gate else None, passed=outcome.passed,
            n_cases=outcome.n_cases, n_failed_cases=outcome.n_failed_cases,
            source=source, ran_at=ran_at, artifact_path=artifact,  # type: ignore[arg-type]
        )

    @app.get("/v1/suites", response_model=list[SuiteInfo])
    def suites(_: None = Depends(auth)) -> list[SuiteInfo]:
        return [
            SuiteInfo(
                name=s.name, scorer=s.scorer, metric=s.metric,
                gate=GateSpec(metric=s.metric, **s.gate) if s.gate else None,
            )
            for s in list_suites()
        ]

    @app.get("/v1/results", response_model=ResultsAggregate)
    def results(_: None = Depends(auth)) -> ResultsAggregate:
        items = st.store.aggregate()
        return ResultsAggregate(results=[_to_run_response(d) for d in items])

    @app.get("/v1/results/{suite}", response_model=RunResponse)
    def results_by_suite(suite: str, _: None = Depends(auth)) -> RunResponse:
        data = st.store.by_suite(suite)
        if data is None:
            raise HTTPException(status_code=404, detail="suite sem rodada registrada")
        return _to_run_response(data)

    @app.get("/health", response_model=Health)
    def health() -> Health:
        deps = {
            "judge_adapter": "enabled" if st.judge is not None else "disabled",
            "results_dir": "ok" if Path(st.settings.results_dir).exists() else "absent",
        }
        status = "ok" if deps["results_dir"] == "ok" else "degraded"
        return Health(status=status, version=VERSION, deps=deps)  # type: ignore[arg-type]

    @app.get("/metrics", response_model=Metrics)
    def metrics(_: None = Depends(auth)) -> Metrics:
        lat = sorted(st.latencies)
        p50 = statistics.median(lat) if lat else 0.0
        p95 = lat[max(0, int(len(lat) * 0.95) - 1)] if lat else 0.0
        return Metrics(
            runs_total=st.runs_total, gates_pass_total=st.gates_pass_total,
            gates_fail_total=st.gates_fail_total,
            latency_ms_p50=round(p50, 2), latency_ms_p95=round(p95, 2),
        )

    add_security_headers(app)
    otel.init_tracing(app, settings)
    return app


def _to_run_response(d: dict[str, Any]) -> RunResponse:
    gate = d.get("gate")
    return RunResponse(
        suite=d["suite"], metric=d["metric"], value=d["value"],
        gate=GateSpec(**gate) if gate else None, passed=d.get("passed"),
        n_cases=d["n_cases"], n_failed_cases=d["n_failed_cases"],
        source=d.get("source", "eval"), ran_at=d.get("ran_at", ""),
        artifact_path=d.get("artifact_path", ""),
    )


app = create_app()
