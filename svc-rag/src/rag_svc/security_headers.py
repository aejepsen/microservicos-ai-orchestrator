"""SEC-03 (FASE 13): headers de segurança defense-in-depth.

APIs são server-to-server (rede internal, sem browser), mas headers são baratos
e cobrem o caso de exposição acidental via proxy/ingress futuro.
"""

from __future__ import annotations

from typing import Any

_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
}


def add_security_headers(app: Any) -> None:
    @app.middleware("http")
    async def _sec_headers(request: Any, call_next: Any) -> Any:
        response = await call_next(request)
        for k, v in _HEADERS.items():
            response.headers.setdefault(k, v)
        return response
