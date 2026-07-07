from __future__ import annotations

import pytest

from obs_svc.model import Source
from obs_svc.scraper import FakeScraper


def test_flatten_numeric() -> None:
    s = FakeScraper({"a": {"source": "live", "x": 3, "y": 4.5}})
    metrics = s.scrape("a", "http://a")
    names = {m.name: m.value for m in metrics}
    assert names == {"x": 3.0, "y": 4.5}


def test_source_field_dropped() -> None:
    s = FakeScraper({"a": {"source": "live", "x": 1}})
    assert all(m.name != "source" for m in s.scrape("a", "http://a"))


def test_all_live() -> None:
    s = FakeScraper({"a": {"x": 1}})
    assert all(m.source is Source.LIVE for m in s.scrape("a", "http://a"))


def test_nested_flattened() -> None:
    s = FakeScraper({"a": {"by_layer": {"semantic": 3, "llm": 1}}})
    names = {m.name for m in s.scrape("a", "http://a")}
    assert names == {"by_layer_semantic", "by_layer_llm"}


def test_bool_ignored() -> None:
    s = FakeScraper({"a": {"flag": True, "x": 1}})
    assert {m.name for m in s.scrape("a", "http://a")} == {"x"}


def test_fake_failure() -> None:
    with pytest.raises(ConnectionError):
        FakeScraper({"a": {"x": 1}}, fail={"a"}).scrape("a", "http://a")


def test_service_attached() -> None:
    s = FakeScraper({"svc-x": {"x": 1}})
    assert all(m.service == "svc-x" for m in s.scrape("svc-x", "http://x"))
