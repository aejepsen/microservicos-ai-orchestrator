"""Auth interna fail-closed + rate-limit por IP + guarda anti-SSRF (QDRANT_URL)."""

from __future__ import annotations

import hmac
import ipaddress
import socket
import time
from collections import deque
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from rag_svc.config import Settings

_MAX_ENTRIES = 10_000
_EVICT_EVERY = 500
_BLOCKED_NETS = [
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
]


def client_ip(request: Request) -> str:
    for header in ("cf-connecting-ip", "x-real-ip"):
        value = request.headers.get(header)
        if value:
            return value.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def verify_internal_key(request: Request, settings: Settings) -> None:
    if not settings.internal_key:
        if settings.allow_open_access:
            return
        raise HTTPException(status_code=401, detail="acesso bloqueado (fail-closed)")
    provided = request.headers.get("x-internal-key", "")
    if not hmac.compare_digest(provided, settings.internal_key):
        raise HTTPException(status_code=401, detail="X-Internal-Key invalida")


def validate_outbound_url(url: str, allow_local: bool) -> None:
    """Anti-SSRF do QDRANT_URL: só http/https; bloqueia metadata/loopback salvo opt-in."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("esquema de URL nao permitido")
    if allow_local:
        return
    host = parsed.hostname or ""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError(f"host nao resolvido: {host}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or any(ip in net for net in _BLOCKED_NETS):
            raise ValueError("URL aponta para rede interna (SSRF bloqueado)")


class RateLimiter:
    def __init__(self, per_minute: int, window_s: float = 60.0) -> None:
        self._per_minute = per_minute
        self._window_s = window_s
        self._hits: dict[str, deque[float]] = {}
        self._calls = 0

    def _evict(self, now: float) -> None:
        stale = [ip for ip, dq in self._hits.items() if not dq or now - dq[-1] > self._window_s]
        for ip in stale:
            del self._hits[ip]
        if len(self._hits) > _MAX_ENTRIES:
            oldest = sorted(self._hits.items(), key=lambda kv: kv[1][-1])
            for ip, _ in oldest[: len(self._hits) - _MAX_ENTRIES]:
                del self._hits[ip]

    def allow(self, ip: str) -> bool:
        now = time.monotonic()
        self._calls += 1
        if self._calls % _EVICT_EVERY == 0:
            self._evict(now)
        dq = self._hits.setdefault(ip, deque())
        while dq and now - dq[0] > self._window_s:
            dq.popleft()
        if len(dq) >= self._per_minute:
            return False
        dq.append(now)
        return True
