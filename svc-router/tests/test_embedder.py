from __future__ import annotations

import numpy as np

from router_svc.embedder import FakeEmbedder, cosine


def test_fake_deterministic() -> None:
    e = FakeEmbedder()
    a = e.encode(["mesma frase"])
    b = e.encode(["mesma frase"])
    assert np.allclose(a, b)


def test_fake_shape() -> None:
    out = FakeEmbedder(dim=16).encode(["a", "b", "c"])
    assert out.shape == (3, 16)


def test_cosine_identical() -> None:
    v = np.array([1.0, 2.0, 3.0])
    assert abs(cosine(v, v) - 1.0) < 1e-9


def test_cosine_orthogonal() -> None:
    assert abs(cosine(np.array([1.0, 0.0]), np.array([0.0, 1.0]))) < 1e-9


def test_cosine_zero_vector() -> None:
    assert cosine(np.zeros(3), np.array([1.0, 2.0, 3.0])) == 0.0


def test_different_texts_differ() -> None:
    e = FakeEmbedder()
    assert not np.allclose(e.encode(["alpha"]), e.encode(["beta"]))
