from __future__ import annotations

import time

from orch_svc.circuit import CircuitBreaker, CircuitOpen, CircuitState


def test_starts_closed() -> None:
    assert CircuitBreaker(3, 30).state is CircuitState.CLOSED


def test_opens_after_threshold() -> None:
    b = CircuitBreaker(3, 30)
    for _ in range(3):
        b.on_transport_failure()
    assert b.state is CircuitState.OPEN


def test_below_threshold_closed() -> None:
    b = CircuitBreaker(3, 30)
    b.on_transport_failure()
    b.on_transport_failure()
    assert b.state is CircuitState.CLOSED


def test_success_resets() -> None:
    b = CircuitBreaker(3, 30)
    b.on_transport_failure()
    b.on_transport_failure()
    b.on_success()
    b.on_transport_failure()
    assert b.state is CircuitState.CLOSED


def test_half_open_after_reset() -> None:
    b = CircuitBreaker(1, 0.05)
    b.on_transport_failure()
    time.sleep(0.06)
    assert b.state is CircuitState.HALF_OPEN


def test_before_call_raises_open() -> None:
    b = CircuitBreaker(1, 30)
    b.on_transport_failure()
    try:
        b.before_call()
        raised = False
    except CircuitOpen:
        raised = True
    assert raised
