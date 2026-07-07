"""Clients dos downstream: interfaces + HttpClients (real) + FakeClients (gates).

Cada chamada propaga `traceparent` (W3C) e usa DOWNSTREAM_KEY. Erros de
transporte viram DownstreamError (contam p/ circuito); 4xx viram
DownstreamBusiness (não contam).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from orch_svc.circuit import DownstreamBusiness, DownstreamError


@dataclass(frozen=True)
class GuardVerdict:
    decision: str  # allow | flag | block
    patterns: list[str]


@dataclass(frozen=True)
class RoutePlan:
    domains: list[str]
    layer: str


@dataclass(frozen=True)
class RagHit:
    text: str
    score: float


# ---- interfaces ----

class GuardrailsClient(Protocol):
    def analyze(self, text: str, trace: str) -> GuardVerdict: ...


class RouterClient(Protocol):
    def route(self, query: str, trace: str) -> RoutePlan: ...


class RagClient(Protocol):
    def search(self, query: str, domain: str, trace: str) -> list[RagHit]: ...


class InferenceClient(Protocol):
    def chat(self, messages: list[dict[str, str]], trace: str) -> str: ...


# ---- HTTP (produção) ----

def _headers(key: str, trace: str) -> dict[str, str]:
    h = {"traceparent": trace}
    if key:
        h["X-Internal-Key"] = key
    return h


@dataclass
class _Http:
    base: str
    key: str
    model: str
    timeout_s: float

    def _post(self, path: str, payload: dict[str, Any], trace: str) -> dict[str, Any]:
        import httpx

        try:
            resp = httpx.post(f"{self.base}{path}", json=payload,
                              headers=_headers(self.key, trace), timeout=self.timeout_s)
        except httpx.HTTPError as exc:
            raise DownstreamError(str(exc)) from exc
        if resp.status_code >= 500:
            raise DownstreamError(f"5xx: {resp.status_code}")
        if resp.status_code >= 400:
            raise DownstreamBusiness(resp.status_code, resp.text[:200])
        return resp.json()


class HttpGuardrails(_Http):
    def analyze(self, text: str, trace: str) -> GuardVerdict:
        payload = {"text": text, "checks": ["sanitize", "injection", "ood"]}
        d = self._post("/v1/analyze", payload, trace)
        inj = d.get("verdicts", {}).get("injection") or {}
        return GuardVerdict(d["decision"], inj.get("patterns", []))


class HttpRouter(_Http):
    def route(self, query: str, trace: str) -> RoutePlan:
        d = self._post("/v1/route", {"query": query}, trace)
        return RoutePlan(d["domains"], d["layer"])


class HttpRag(_Http):
    def search(self, query: str, domain: str, trace: str) -> list[RagHit]:
        d = self._post("/v1/search", {"query": query, "collection": domain, "top_k": 3}, trace)
        return [RagHit(h["text"], h["score"]) for h in d.get("hits", [])]


class HttpInference(_Http):
    def chat(self, messages: list[dict[str, str]], trace: str) -> str:
        d = self._post("/v1/chat/completions", {"model": self.model, "messages": messages}, trace)
        return d["choices"][0]["message"]["content"]


# ---- Fakes (gates) ----

@dataclass
class FakeGuardrails:
    verdict: str = "allow"
    calls: list[str] = field(default_factory=list)

    def analyze(self, text: str, trace: str) -> GuardVerdict:
        self.calls.append(trace)
        pats = ["ignore_instructions"] if self.verdict == "block" else []
        return GuardVerdict(self.verdict, pats)


@dataclass
class FakeRouter:
    domains: list[str] = field(default_factory=lambda: ["financas"])
    layer: str = "semantic"
    calls: list[str] = field(default_factory=list)

    def route(self, query: str, trace: str) -> RoutePlan:
        self.calls.append(trace)
        return RoutePlan(list(self.domains), self.layer)


@dataclass
class FakeRag:
    hits: int = 2
    calls: list[str] = field(default_factory=list)

    def search(self, query: str, domain: str, trace: str) -> list[RagHit]:
        self.calls.append(trace)
        return [RagHit(f"contexto {domain} {i}", 0.9 - i * 0.1) for i in range(self.hits)]


@dataclass
class FakeInference:
    fail_transport: bool = False
    calls: list[str] = field(default_factory=list)

    def chat(self, messages: list[dict[str, str]], trace: str) -> str:
        self.calls.append(trace)
        if self.fail_transport:
            raise DownstreamError("fake: inference fora")
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return f"resposta para: {user[:40]}"
