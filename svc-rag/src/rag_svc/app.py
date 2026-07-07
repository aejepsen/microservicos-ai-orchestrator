"""svc-rag — API FastAPI. Swagger off; stack só em log."""

from __future__ import annotations

import logging
import statistics
import time
from collections import deque
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from rag_svc.community import CommunityStore
from rag_svc.config import VERSION, Settings, load_settings
from rag_svc.embedder import FakeEmbedder, SbertEmbedder
from rag_svc.ingest import ingest_documents, search_documents
from rag_svc.schemas import (
    CollectionInfo,
    CommunitySummary,
    Health,
    Hit,
    IngestRequest,
    IngestResponse,
    Metrics,
    SearchRequest,
    SearchResponse,
)
from rag_svc.security import (
    RateLimiter,
    client_ip,
    validate_outbound_url,
    verify_internal_key,
)
from rag_svc.store import InMemoryStore, QdrantStore, VectorStore

logger = logging.getLogger("rag")


class State:
    def __init__(self, settings: Settings, embedder: Any = "auto", store: Any = "auto") -> None:
        self.settings = settings
        self.rate_limiter = RateLimiter(settings.rate_limit_per_min)
        self.embedder = self._build_embedder(settings) if embedder == "auto" else embedder
        self.store: VectorStore = self._build_store(settings) if store == "auto" else store
        self.communities = CommunityStore(settings.models_dir)
        self.ingests_total = 0
        self.searches_total = 0
        self.chunks_total = 0
        self.latencies: deque[float] = deque(maxlen=1000)

    @staticmethod
    def _build_embedder(settings: Settings) -> Any:
        try:
            return SbertEmbedder(settings.embed_model)
        except Exception as exc:  # noqa: BLE001 — degradação declarada
            logger.warning("embedder indisponivel: %s", exc)
            return None

    @staticmethod
    def _build_store(settings: Settings) -> VectorStore:
        if settings.vector_store == "memory":
            return InMemoryStore()
        try:
            validate_outbound_url(settings.qdrant_url, settings.allow_local_store)
        except ValueError as exc:
            logger.error("QDRANT_URL invalida: %s — usando memory", exc)
            return InMemoryStore()
        return QdrantStore(settings.qdrant_url, settings.qdrant_api_key)


def create_app(settings: Settings | None = None, state: State | None = None) -> FastAPI:
    settings = settings or load_settings()
    logging.basicConfig(level=settings.log_level)
    if settings.allow_open_access and not settings.internal_key:
        logger.warning("ALLOW_OPEN_ACCESS=1 sem INTERNAL_KEY — modo aberto (dev)")
    st = state or State(settings)

    app = FastAPI(title="svc-rag", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.rag = st

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

    def _require_deps() -> None:
        if st.embedder is None:
            raise HTTPException(status_code=503, detail="embedder indisponivel")

    @app.post("/v1/ingest", response_model=IngestResponse)
    def ingest(req: IngestRequest, _: None = Depends(auth)) -> Any:
        _require_deps()
        for doc in req.documents:
            if len(doc.text) > st.settings.max_doc_chars:
                return JSONResponse(
                    status_code=422,
                    content={"error": "doc_grande", "detail": f"doc {doc.id} excede MAX_DOC_CHARS",
                             "rule": "ingest"},
                )
        start = time.perf_counter()
        try:
            res = ingest_documents(
                [d.model_dump() for d in req.documents], req.collection, st.embedder, st.store,
                max_chars=st.settings.chunk_max_chars, overlap=st.settings.chunk_overlap,
            )
        except Exception as exc:  # noqa: BLE001 — store fora vira 503
            raise HTTPException(
                status_code=503, detail=f"vector store indisponivel: {exc}"
            ) from exc
        st.ingests_total += 1
        st.chunks_total += res.n_chunks
        st.latencies.append((time.perf_counter() - start) * 1000.0)
        return IngestResponse(collection=req.collection, **res.__dict__)

    @app.post("/v1/search", response_model=SearchResponse)
    def search(req: SearchRequest, _: None = Depends(auth)) -> Any:
        _require_deps()
        start = time.perf_counter()
        try:
            hits = search_documents(req.query, req.collection, req.top_k, st.embedder, st.store)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=503, detail=f"vector store indisponivel: {exc}"
            ) from exc
        latency_ms = (time.perf_counter() - start) * 1000.0
        st.searches_total += 1
        st.latencies.append(latency_ms)
        logger.info(
            '{"event":"search","collection":%r,"n_hits":%d,"latency_ms":%.1f}',
            req.collection, len(hits), latency_ms,
        )
        return SearchResponse(
            query=req.query, collection=req.collection,
            hits=[Hit(chunk_id=h.chunk_id, doc_id=h.doc_id, text=h.text,
                      score=round(h.score, 4), metadata=h.metadata) for h in hits],
        )

    @app.get("/v1/collections", response_model=list[CollectionInfo])
    def collections(_: None = Depends(auth)) -> list[CollectionInfo]:
        return [CollectionInfo(name=c, n_chunks=st.store.count(c)) for c in st.store.collections()]

    @app.get("/v1/community/{cid}", response_model=CommunitySummary)
    def community(cid: str, _: None = Depends(auth)) -> Any:
        if not (st.settings.graphrag_enabled and st.communities.available):
            raise HTTPException(status_code=503, detail="GraphRAG desligado ou sem artefato")
        c = st.communities.get(cid)
        if c is None:
            raise HTTPException(status_code=404, detail="comunidade inexistente")
        return CommunitySummary(id=str(c["id"]), title=c.get("title", ""),
                                summary=c.get("summary", ""), members=c.get("members", []))

    @app.get("/health", response_model=Health)
    def health() -> Health:
        store_ok = True
        try:
            st.store.collections()
        except Exception:  # noqa: BLE001
            store_ok = False
        deps = {
            "embedder": "ok" if st.embedder is not None else "down",
            "vector_store": "ok" if store_ok else "down",
            "graphrag": (
                "enabled"
                if (st.settings.graphrag_enabled and st.communities.available)
                else "absent"
            ),
        }
        status = "ok" if deps["embedder"] == "ok" and store_ok else "degraded"
        return Health(status=status, version=VERSION, deps=deps)  # type: ignore[arg-type]

    @app.get("/metrics", response_model=Metrics)
    def metrics(_: None = Depends(auth)) -> Metrics:
        lat = sorted(st.latencies)
        p50 = statistics.median(lat) if lat else 0.0
        p95 = lat[max(0, int(len(lat) * 0.95) - 1)] if lat else 0.0
        return Metrics(
            ingests_total=st.ingests_total, searches_total=st.searches_total,
            chunks_total=st.chunks_total,
            latency_ms_p50=round(p50, 2), latency_ms_p95=round(p95, 2),
        )

    return app


app = create_app()

__all__ = ["create_app", "State", "FakeEmbedder", "InMemoryStore"]
