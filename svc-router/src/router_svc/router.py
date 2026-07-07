"""Núcleo de roteamento em 3 camadas: semântica híbrida → guards → fallback LLM."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from router_svc.bm25 import BM25, ranks_from_scores, rrf_fuse
from router_svc.embedder import Embedder, cosine
from router_svc.guards import apply_guards
from router_svc.llm import LLMClassifier


@dataclass(frozen=True)
class RoutePlan:
    domains: list[str]
    layer: str
    scores: dict[str, float]
    llm_used: bool


class LLMUnavailable(Exception):
    """Camada LLM exigida mas indisponível/sem soft-fallback."""


@dataclass
class RouteIndex:
    """Índice de uma rota: exemplares + seus embeddings (computados no boot)."""

    name: str
    exemplars: list[str]
    embeddings: np.ndarray


class Router:
    def __init__(
        self,
        routes: list[tuple[str, list[str]]],
        embedder: Embedder | None,
        *,
        threshold: float,
        tie_margin: float,
        rrf_k: int,
        hybrid: bool,
    ) -> None:
        self._embedder = embedder
        self._threshold = threshold
        self._tie_margin = tie_margin
        self._rrf_k = rrf_k
        self._hybrid = hybrid
        self._routes = [name for name, _ in routes]
        self._exemplars = [ex for _, exs in routes for ex in exs]
        # mapa exemplar-global -> índice da rota
        self._exemplar_route: list[int] = []
        for ri, (_, exs) in enumerate(routes):
            self._exemplar_route.extend([ri] * len(exs))
        self._bm25 = BM25(self._exemplars) if self._exemplars else None
        self._index: np.ndarray | None = None
        if embedder is not None and self._exemplars:
            self._index = embedder.encode(self._exemplars)

    @property
    def semantic_available(self) -> bool:
        return self._index is not None

    def _dense_route_scores(self, qvec: np.ndarray) -> list[float]:
        assert self._index is not None
        per_route = [-1.0] * len(self._routes)
        for gi, evec in enumerate(self._index):
            ri = self._exemplar_route[gi]
            per_route[ri] = max(per_route[ri], cosine(qvec, evec))
        return [max(0.0, s) for s in per_route]

    def _lexical_route_scores(self, query: str) -> list[float]:
        assert self._bm25 is not None
        ex_scores = self._bm25.scores(query)
        per_route = [0.0] * len(self._routes)
        for gi, s in enumerate(ex_scores):
            ri = self._exemplar_route[gi]
            per_route[ri] = max(per_route[ri], s)
        return per_route

    def route(
        self,
        query: str,
        *,
        allow_llm: bool,
        llm: LLMClassifier | None,
        soft_fallback: bool = False,
    ) -> RoutePlan:
        dense: list[float] | None = None
        scores: dict[str, float] = {}
        semantic_domains: list[str] = []
        top_dense = 0.0

        if self.semantic_available:
            qvec = self._embedder.encode([query])[0]  # type: ignore[union-attr]
            dense = self._dense_route_scores(qvec)
            if self._hybrid and self._bm25 is not None:
                lexical = self._lexical_route_scores(query)
                fused = rrf_fuse(ranks_from_scores(dense), ranks_from_scores(lexical), self._rrf_k)
                winner = int(np.argmax(fused))
            else:
                winner = int(np.argmax(dense))
            scores = {self._routes[i]: round(dense[i], 4) for i in range(len(self._routes))}
            top_dense = dense[winner]
            if top_dense >= self._threshold:
                # argmax + empates dentro da margem (multi-domínio)
                semantic_domains = [
                    self._routes[i]
                    for i in range(len(self._routes))
                    if dense[i] >= top_dense - self._tie_margin
                ]

        guard_domains, _fired = apply_guards(query)

        # Camada semântica decidiu → guards apenas adicionam.
        if semantic_domains:
            domains = list(dict.fromkeys(semantic_domains + sorted(guard_domains)))
            return RoutePlan(domains, "semantic", scores, llm_used=False)

        # Guards decidiram (semântica não passou do threshold).
        if guard_domains:
            return RoutePlan(sorted(guard_domains), "lexical", scores, llm_used=False)

        # Fallback LLM.
        if allow_llm and llm is not None:
            picked = llm.classify(query, self._routes)
            if picked:
                return RoutePlan(picked, "llm", scores, llm_used=True)

        if allow_llm and llm is None and not soft_fallback:
            raise LLMUnavailable("camada LLM exigida e indisponivel")

        # Soft-fallback: melhor palpite semântico (ou primeira rota se sem embedder).
        best = [self._routes[int(np.argmax(dense))]] if dense else self._routes[:1]
        return RoutePlan(best, "fallback", scores, llm_used=False)
