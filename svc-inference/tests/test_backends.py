from __future__ import annotations

import pytest

from inference.backends import FakeBackend, build_backend
from inference.circuit import BackendBusiness, BackendError
from inference.config import Settings


def test_fake_chat_usage_from_source() -> None:
    b = FakeBackend(reply="a b c")
    comp = b.chat("m", [{"role": "user", "content": "um dois"}])
    assert comp.usage.prompt_tokens == 2
    assert comp.usage.completion_tokens == 3
    assert comp.usage.total_tokens == 5
    assert comp.finish_reason == "stop"


def test_fake_stream_chunks_and_final_usage() -> None:
    b = FakeBackend(reply="um dois tres quatro", n_chunks=2)
    chunks = list(b.chat_stream("m", [{"role": "user", "content": "oi"}]))
    assert chunks[-1].finish_reason == "stop"
    assert chunks[-1].usage is not None
    assert all(c.usage is None for c in chunks[:-1])
    assert "".join(c.delta for c in chunks).split() == ["um", "dois", "tres", "quatro"]


def test_fake_transport_failure() -> None:
    with pytest.raises(BackendError):
        FakeBackend(fail_transport=True).chat("m", [{"role": "user", "content": "x"}])


def test_fake_business_failure() -> None:
    with pytest.raises(BackendBusiness) as ei:
        FakeBackend(fail_business=422).chat("m", [{"role": "user", "content": "x"}])
    assert ei.value.status == 422


def test_fake_list_models() -> None:
    assert FakeBackend().list_models() == ["fake-model"]


def test_build_backend_fake() -> None:
    assert isinstance(build_backend(Settings(backend="fake")), FakeBackend)


def test_build_backend_ollama() -> None:
    from inference.backends import OllamaBackend

    assert isinstance(build_backend(Settings(backend="ollama")), OllamaBackend)
