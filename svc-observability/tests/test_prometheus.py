from __future__ import annotations

import re

from obs_svc.model import Metric, Source
from obs_svc.prometheus import render

_LINE_RE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)\{([^}]*)\}\s+(-?[\d.eE+]+)$')


def test_help_and_type() -> None:
    text = render([Metric("x_total", 1, Source.LIVE, "svc")])
    assert "# HELP x_total" in text
    assert "# TYPE x_total gauge" in text


def test_data_line_parses() -> None:
    text = render([Metric("x_total", 5, Source.LIVE, "svc")])
    data = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
    assert all(_LINE_RE.match(ln) for ln in data)


def test_labels_present() -> None:
    text = render([Metric("x", 1, Source.EVAL, "svc-evals")])
    assert 'service="svc-evals"' in text and 'source="eval"' in text


def test_name_sanitized() -> None:
    text = render([Metric("weird name!", 1, Source.LIVE, "svc")])
    assert "weird_name_" in text


def test_label_escaped() -> None:
    text = render([Metric("x", 1, Source.LIVE, 'has"quote')])
    assert '\\"quote' in text


def test_help_deduped() -> None:
    text = render([Metric("x", 1, Source.LIVE, "a"), Metric("x", 2, Source.LIVE, "b")])
    assert text.count("# HELP x ") == 1


def test_estimate_labeled() -> None:
    text = render([Metric("proj", 1, Source.ESTIMATE, "ecosystem")])
    assert 'source="estimate"' in text
