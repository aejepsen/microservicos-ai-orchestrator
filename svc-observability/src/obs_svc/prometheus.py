"""Exposição em texto Prometheus. Formato: # HELP / # TYPE / name{labels} value.

Nome sanitizado para [a-zA-Z0-9_:]; labels service e source; valores de label
com escape de \\ e ".
"""

from __future__ import annotations

import re

from obs_svc.model import Metric

_NAME_RE = re.compile(r"[^a-zA-Z0-9_:]")


def _sanitize_name(name: str) -> str:
    s = _NAME_RE.sub("_", name)
    return s if not s[:1].isdigit() else f"_{s}"


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def render(metrics: list[Metric]) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for m in metrics:
        pname = _sanitize_name(m.name)
        if pname not in seen:
            lines.append(f"# HELP {pname} agregado do ecossistema")
            lines.append(f"# TYPE {pname} gauge")
            seen.add(pname)
        labels = (
            f'service="{_escape_label(m.service)}",'
            f'source="{_escape_label(str(m.source))}",'
            f'stale="{str(m.stale).lower()}"'
        )
        lines.append(f"{pname}{{{labels}}} {m.value}")
    return "\n".join(lines) + "\n"
