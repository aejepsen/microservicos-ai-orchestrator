"""Circuit breaker por backend (padrão AI-Orchestrator).

3 falhas de transporte → OPEN por reset_s → half-open (1 tentativa).
4xx do backend NÃO conta como falha (é regra de negócio, não indisponibilidade).
"""

from __future__ import annotations

import time
from enum import StrEnum


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class BackendError(Exception):
    """Falha de transporte (conta para o circuito)."""


class BackendBusiness(Exception):
    """Erro 4xx do backend (NÃO conta para o circuito)."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class CircuitOpen(Exception):
    """Circuito OPEN — request recusado sem bater no backend."""


class CircuitBreaker:
    def __init__(self, fail_threshold: int, reset_s: float) -> None:
        self._threshold = fail_threshold
        self._reset_s = reset_s
        self._failures = 0
        self._opened_at = 0.0
        self._state = CircuitState.CLOSED

    @property
    def state(self) -> CircuitState:
        if self._state is CircuitState.OPEN and time.monotonic() - self._opened_at >= self._reset_s:
            self._state = CircuitState.HALF_OPEN
        return self._state

    def before_call(self) -> None:
        if self.state is CircuitState.OPEN:
            raise CircuitOpen("circuito OPEN")

    def on_success(self) -> None:
        self._failures = 0
        self._state = CircuitState.CLOSED

    def on_transport_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold or self._state is CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
