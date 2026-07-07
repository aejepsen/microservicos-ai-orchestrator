"""OOD guard: fit rejeita clarification, exige mínimo, persiste, separa in/out."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeEmbedder

from guardrails.ood import MIN_FIT_SAMPLES, OodGuard


def _corpus(n: int) -> list[dict]:
    return [{"text": f"Qual o saldo da conta {i}?"} for i in range(n)]


def test_fit_rejects_clarification(tmp_path: Path) -> None:
    guard = OodGuard(str(tmp_path))
    corpus = _corpus(35) + [{"text": "hmm nao sei", "is_clarification": True}]
    report = guard.fit(corpus, [f"receita de bolo {i}" for i in range(12)], FakeEmbedder())
    assert report.n_rejected_clarification == 1
    assert report.n_samples == 35


def test_fit_requires_minimum(tmp_path: Path) -> None:
    guard = OodGuard(str(tmp_path))
    import pytest

    with pytest.raises(ValueError, match="insuficiente"):
        guard.fit(_corpus(MIN_FIT_SAMPLES - 1), ["x" * 5 for _ in range(12)], FakeEmbedder())


def test_fit_persists_and_reloads(tmp_path: Path) -> None:
    OodGuard(str(tmp_path)).fit(_corpus(35), [f"tema alheio {i}" for i in range(12)], FakeEmbedder())
    assert (tmp_path / "ood_subspace.npz").exists()
    assert (tmp_path / "ood_meta.json").exists()
    reloaded = OodGuard(str(tmp_path))
    assert reloaded.fitted


def test_unfitted_reports_absent(tmp_path: Path) -> None:
    assert not OodGuard(str(tmp_path)).fitted
