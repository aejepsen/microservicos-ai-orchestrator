from __future__ import annotations

from pathlib import Path

from evals_svc.results_store import ResultsStore


def _payload(suite: str, value: float) -> dict:
    return {"suite": suite, "metric": "pass_rate", "value": value, "gate": None,
            "passed": None, "n_cases": 1, "n_failed_cases": 0, "source": "eval",
            "ran_at": "2026-07-06T00:00:00", "artifact_path": ""}


def test_write_and_read(tmp_path: Path) -> None:
    store = ResultsStore(str(tmp_path), cache_ttl_s=0)
    path = store.write("suiteA", _payload("suiteA", 0.9))
    assert Path(path).exists()
    assert store.by_suite("suiteA")["value"] == 0.9


def test_latest_wins(tmp_path: Path) -> None:
    store = ResultsStore(str(tmp_path), cache_ttl_s=0)
    store.write("s", _payload("s", 0.1))
    import time

    time.sleep(1.05)  # timestamps têm resolução de 1s no nome
    store.write("s", _payload("s", 0.9))
    assert store.by_suite("s")["value"] == 0.9


def test_aggregate_one_per_suite(tmp_path: Path) -> None:
    store = ResultsStore(str(tmp_path), cache_ttl_s=0)
    store.write("a", _payload("a", 0.5))
    store.write("b", _payload("b", 0.6))
    agg = store.aggregate()
    assert {r["suite"] for r in agg} == {"a", "b"}


def test_missing_suite_none(tmp_path: Path) -> None:
    assert ResultsStore(str(tmp_path), cache_ttl_s=0).by_suite("nao_existe") is None


def test_cache_reused(tmp_path: Path) -> None:
    store = ResultsStore(str(tmp_path), cache_ttl_s=999)
    store.write("a", _payload("a", 0.5))
    first = store.aggregate()
    assert first is store.aggregate()  # mesmo objeto (cache)
