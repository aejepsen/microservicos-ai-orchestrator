"""Backends de inferência: interface + FakeBackend (gates) + OllamaBackend (real).

Usage é lido NA FONTE (o backend reporta prompt/completion tokens). A fachada
nunca estima. FakeBackend é determinístico para gates 100% offline.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from inference.circuit import BackendBusiness, BackendError


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class Completion:
    content: str
    finish_reason: str
    usage: Usage


@dataclass(frozen=True)
class Chunk:
    delta: str
    finish_reason: str | None = None
    usage: Usage | None = None  # presente apenas no último chunk


class Backend(Protocol):
    def chat(self, model: str, messages: list[dict[str, str]], **opts: Any) -> Completion: ...
    def chat_stream(
        self, model: str, messages: list[dict[str, str]], **opts: Any
    ) -> Iterator[Chunk]: ...
    def list_models(self) -> list[str]: ...


def _count_tokens(text: str) -> int:
    """Aproximação simples por palavras — usada SÓ pelo FakeBackend como usage sintético."""
    return len(text.split())


@dataclass
class FakeBackend:
    """Determinístico para gates. Configurável para falhar (resiliência)."""

    reply: str = "resposta determinística do fake backend"
    models: list[str] = field(default_factory=lambda: ["fake-model"])
    fail_transport: bool = False       # simula backend fora (conta p/ circuito)
    fail_business: int = 0             # simula 4xx (NÃO conta p/ circuito)
    n_chunks: int = 3

    def _guard(self) -> None:
        if self.fail_transport:
            raise BackendError("fake: transporte fora")
        if self.fail_business:
            raise BackendBusiness(self.fail_business, "fake: erro de negocio")

    def _usage(self, messages: list[dict[str, str]]) -> Usage:
        prompt = " ".join(m["content"] for m in messages)
        pt = _count_tokens(prompt)
        ct = _count_tokens(self.reply)
        return Usage(pt, ct, pt + ct)

    def chat(self, model: str, messages: list[dict[str, str]], **opts: Any) -> Completion:
        self._guard()
        return Completion(self.reply, "stop", self._usage(messages))

    def chat_stream(
        self, model: str, messages: list[dict[str, str]], **opts: Any
    ) -> Iterator[Chunk]:
        self._guard()
        words = self.reply.split()
        step = max(1, len(words) // self.n_chunks)
        pieces = [" ".join(words[i : i + step]) for i in range(0, len(words), step)]
        for i, piece in enumerate(pieces):
            last = i == len(pieces) - 1
            yield Chunk(
                delta=piece + ("" if last else " "),
                finish_reason="stop" if last else None,
                usage=self._usage(messages) if last else None,
            )

    def list_models(self) -> list[str]:
        self._guard()
        return list(self.models)


@dataclass
class OllamaBackend:
    """Backend real via HTTP Ollama. Usage na fonte (prompt_eval_count/eval_count)."""

    url: str
    timeout_s: float

    def _client(self) -> Any:
        import httpx

        return httpx.Client(timeout=self.timeout_s, base_url=self.url.rstrip("/"))

    @staticmethod
    def _usage(data: dict[str, Any]) -> Usage:
        pt = int(data.get("prompt_eval_count", 0))
        ct = int(data.get("eval_count", 0))
        return Usage(pt, ct, pt + ct)

    def chat(self, model: str, messages: list[dict[str, str]], **opts: Any) -> Completion:
        import httpx

        try:
            with self._client() as c:
                resp = c.post(
                    "/api/chat",
                    json={"model": model, "messages": messages, "stream": False},
                )
        except httpx.HTTPError as exc:
            raise BackendError(str(exc)) from exc
        if resp.status_code >= 500:
            raise BackendError(f"backend 5xx: {resp.status_code}")
        if resp.status_code >= 400:
            raise BackendBusiness(resp.status_code, resp.text[:200])
        data = resp.json()
        return Completion(
            data["message"]["content"], data.get("done_reason", "stop"), self._usage(data)
        )

    def chat_stream(
        self, model: str, messages: list[dict[str, str]], **opts: Any
    ) -> Iterator[Chunk]:
        import json as _json

        import httpx

        try:
            with self._client() as c, c.stream(
                "POST", "/api/chat", json={"model": model, "messages": messages, "stream": True}
            ) as resp:
                if resp.status_code >= 500:
                    raise BackendError(f"backend 5xx: {resp.status_code}")
                if resp.status_code >= 400:
                    raise BackendBusiness(resp.status_code, "erro de negocio")
                for line in resp.iter_lines():
                    if not line:
                        continue
                    data = _json.loads(line)
                    done = data.get("done", False)
                    yield Chunk(
                        delta=data.get("message", {}).get("content", ""),
                        finish_reason=data.get("done_reason", "stop") if done else None,
                        usage=self._usage(data) if done else None,
                    )
        except httpx.HTTPError as exc:
            raise BackendError(str(exc)) from exc

    def list_models(self) -> list[str]:
        import httpx

        try:
            with self._client() as c:
                resp = c.get("/api/tags")
        except httpx.HTTPError as exc:
            raise BackendError(str(exc)) from exc
        if resp.status_code >= 400:
            raise BackendError(f"backend {resp.status_code}")
        return [m["name"] for m in resp.json().get("models", [])]


def build_backend(settings: Any) -> Backend:
    if settings.backend == "fake":
        return FakeBackend()
    return OllamaBackend(settings.backend_url, settings.backend_timeout_s)
