"""Grafo de orquestração: sanitize → route → fan-out → HITL → fan-in.

Emite eventos (para SSE ou coleta). Guardrails é fail-closed: fora → recusa.
Cada downstream passa por seu circuit breaker e recebe o traceparent.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from orch_svc.circuit import CircuitBreaker, CircuitOpen, DownstreamBusiness, DownstreamError
from orch_svc.clients import (
    GuardrailsClient,
    InferenceClient,
    RagClient,
    RouterClient,
)
from orch_svc.write_intent import is_write_intent


@dataclass
class Event:
    type: str  # route | agent | final | blocked | paused | error
    data: dict[str, Any]


@dataclass
class Thread:
    thread_id: str
    query: str
    decision: str = "answered"
    domains: list[str] = field(default_factory=list)
    agents: list[dict[str, Any]] = field(default_factory=list)
    final: str | None = None
    pending_write: dict[str, Any] | None = None


def new_traceparent() -> str:
    """W3C traceparent: version(00)-traceid(32hex)-spanid(16hex)-flags(01)."""
    return f"00-{uuid.uuid4().hex}-{uuid.uuid4().hex[:16]}-01"


class Breakers:
    def __init__(self, threshold: int, reset_s: float) -> None:
        self.guardrails = CircuitBreaker(threshold, reset_s)
        self.router = CircuitBreaker(threshold, reset_s)
        self.rag = CircuitBreaker(threshold, reset_s)
        self.inference = CircuitBreaker(threshold, reset_s)


class DownstreamUnavailable(Exception):
    def __init__(self, service: str) -> None:
        super().__init__(service)
        self.service = service


class GuardrailsBlocked(Exception):
    def __init__(self, patterns: list[str]) -> None:
        super().__init__("blocked")
        self.patterns = patterns


class Orchestrator:
    def __init__(
        self,
        guardrails: GuardrailsClient,
        router: RouterClient,
        rag: RagClient | None,
        inference: InferenceClient,
        breakers: Breakers,
        *,
        hitl_enabled: bool,
    ) -> None:
        self._g = guardrails
        self._r = router
        self._rag = rag
        self._inf = inference
        self._b = breakers
        self._hitl = hitl_enabled

    def _call(self, breaker: CircuitBreaker, service: str, fn: Any) -> Any:
        try:
            breaker.before_call()
            out = fn()
            breaker.on_success()
            return out
        except DownstreamBusiness as exc:
            raise DownstreamUnavailable(service) from exc  # 4xx: 503, não abre circuito
        except (DownstreamError, CircuitOpen) as exc:
            if isinstance(exc, DownstreamError):
                breaker.on_transport_failure()
            raise DownstreamUnavailable(service) from exc

    def run(self, thread: Thread, trace: str, *, allow_write: bool) -> Iterator[Event]:
        # 1. Guardrails (FAIL-CLOSED: fora → recusa, não segue sem análise).
        verdict = self._call(self._b.guardrails, "guardrails",
                             lambda: self._g.analyze(thread.query, trace))
        if verdict.decision == "block":
            thread.decision = "blocked"
            yield Event("blocked", {"patterns": verdict.patterns})
            return

        # 2. Route.
        plan = self._call(self._b.router, "router", lambda: self._r.route(thread.query, trace))
        thread.domains = plan.domains
        yield Event("route", {"domains": plan.domains, "layer": plan.layer})

        # 3. HITL: write intent + não aprovado → pausa antes do fan-out.
        if self._hitl and not allow_write and is_write_intent(thread.query):
            thread.decision = "paused"
            thread.pending_write = {"query": thread.query, "domains": plan.domains}
            yield Event("paused", {"domains": plan.domains, "reason": "write_intent"})
            return

        yield from self._fan_out_in(thread, trace)

    def _fan_out_in(self, thread: Thread, trace: str) -> Iterator[Event]:
        # 4. Fan-out: um agente por domínio (rag + inference). Falha parcial marca o domínio.
        answers: list[dict[str, Any]] = []
        for domain in thread.domains:
            context: list[str] = []
            if self._rag is not None:
                try:
                    hits = self._call(self._b.rag, "rag",
                                     lambda d=domain: self._rag.search(thread.query, d, trace))
                    context = [h.text for h in hits]
                except DownstreamUnavailable:
                    context = []  # rag é opcional: segue sem contexto
            messages = [
                {"role": "system", "content": f"Domínio {domain}. Contexto: {' | '.join(context)}"},
                {"role": "user", "content": thread.query},
            ]
            try:
                answer = self._call(self._b.inference, "inference",
                                    lambda m=messages: self._inf.chat(m, trace))
            except DownstreamUnavailable:
                yield Event("error", {"domain": domain, "detail": "inference indisponivel"})
                answer = f"[{domain}: indisponível]"
            result = {"domain": domain, "answer": answer, "context_used": len(context)}
            answers.append(result)
            thread.agents.append(result)
            yield Event("agent", result)

        # 5. Fan-in: síntese (multi-domínio) ou resposta direta (single).
        if len(answers) == 1:
            thread.final = answers[0]["answer"]
        else:
            combined = "\n".join(f"[{a['domain']}] {a['answer']}" for a in answers)
            messages = [
                {"role": "system", "content": "Sintetize as respostas dos domínios."},
                {"role": "user", "content": combined},
            ]
            try:
                thread.final = self._call(self._b.inference, "inference",
                                          lambda: self._inf.chat(messages, trace))
            except DownstreamUnavailable:
                thread.final = combined  # degradação: entrega o combinado bruto
        thread.decision = "answered"
        yield Event("final", {"final": thread.final})

    def resume(self, thread: Thread, trace: str, *, approve: bool) -> Iterator[Event]:
        if not approve:
            thread.decision = "answered"
            thread.pending_write = None
            thread.final = "Operação de escrita rejeitada pelo usuário."
            yield Event("final", {"final": thread.final})
            return
        thread.pending_write = None
        yield from self._fan_out_in(thread, trace)
