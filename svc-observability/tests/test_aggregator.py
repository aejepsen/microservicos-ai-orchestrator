from __future__ import annotations

from obs_svc.aggregator import Aggregator
from obs_svc.model import Source
from obs_svc.scraper import FakeScraper
from obs_svc.upstreams import Upstream

UPS = [Upstream("a", "http://a"), Upstream("b", "http://b")]
PAY = {"a": {"x": 1, "tokens_input_total": 10}, "b": {"y": 2, "tokens_output_total": 5}}


def test_refresh_all_ok() -> None:
    agg = Aggregator(UPS, FakeScraper(PAY))
    ok, failed = agg.refresh()
    assert ok == 2 and failed == 0


def test_overview_merges() -> None:
    agg = Aggregator(UPS, FakeScraper(PAY))
    agg.refresh()
    names = {(m.service, m.name) for m in agg.overview()}
    assert ("a", "x") in names and ("b", "y") in names


def test_derived_is_estimate() -> None:
    agg = Aggregator(UPS, FakeScraper(PAY))
    agg.refresh()
    derived = [m for m in agg.overview() if m.name == "ecosystem_tokens_total"]
    assert len(derived) == 1
    assert derived[0].source is Source.ESTIMATE
    assert derived[0].value == 15.0


def test_ingest_eval_source() -> None:
    agg = Aggregator(UPS, FakeScraper(PAY))
    n = agg.ingest_eval("svc-evals", "2026-07-04", [{"name": "faithfulness", "value": 0.975}])
    assert n == 1
    ev = [m for m in agg.overview() if m.source is Source.EVAL]
    assert ev[0].name == "faithfulness" and ev[0].ts == "2026-07-04"


def test_failed_upstream_partial() -> None:
    agg = Aggregator(UPS, FakeScraper(PAY, fail={"b"}))
    ok, failed = agg.refresh()
    assert ok == 1 and failed == 1
    assert {s.name: s.ok for s in agg.services()} == {"a": True, "b": False}


def test_stale_kept_on_failure() -> None:
    agg = Aggregator(UPS, FakeScraper(PAY))
    agg.refresh()
    agg._scraper = FakeScraper(PAY, fail={"b"})
    agg.refresh()
    b_metrics = [m for m in agg.overview() if m.service == "b"]
    assert b_metrics and all(m.stale for m in b_metrics)


def test_upstreams_up() -> None:
    agg = Aggregator(UPS, FakeScraper(PAY, fail={"a"}))
    agg.refresh()
    assert agg.upstreams_up() == 1
