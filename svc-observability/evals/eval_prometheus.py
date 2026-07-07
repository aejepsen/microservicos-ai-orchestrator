"""G4 — exposição Prometheus: texto parseável (HELP/TYPE/linhas), labels corretos."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from obs_svc.model import Metric, Source  # noqa: E402
from obs_svc.prometheus import render  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"

_LINE_RE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)\{([^}]*)\}\s+(-?[\d.eE+]+)$')


def main() -> int:
    checks: list[tuple[str, bool]] = []
    metrics = [
        Metric("requests_total", 10, Source.LIVE, "svc-router"),
        Metric("faithfulness", 0.975, Source.EVAL, "svc-evals"),
        Metric("ecosystem_tokens_total", 150, Source.ESTIMATE, "ecosystem"),
        Metric("weird name!", 3, Source.LIVE, "svc-x"),  # nome sanitizado
    ]
    text = render(metrics)
    lines = text.splitlines()

    help_lines = [ln for ln in lines if ln.startswith("# HELP")]
    type_lines = [ln for ln in lines if ln.startswith("# TYPE")]
    data_lines = [ln for ln in lines if ln and not ln.startswith("#")]

    checks.append(("has_help", len(help_lines) >= 3))
    checks.append(("has_type", len(type_lines) >= 3))
    checks.append(("all_data_parse", all(_LINE_RE.match(ln) for ln in data_lines)))

    # source aparece como label em cada linha
    checks.append(("source_label", all('source="' in ln for ln in data_lines)))
    checks.append(("service_label", all('service="' in ln for ln in data_lines)))

    # nome sanitizado: 'weird name!' -> weird_name_
    checks.append(("name_sanitized", any(ln.startswith("weird_name_") for ln in data_lines)))

    # estimate rotulado corretamente
    checks.append(("estimate_labeled", any('source="estimate"' in ln for ln in data_lines)))

    wrong = [n for n, ok in checks if not ok]
    passed = not wrong
    print(f"[G4] checks={len(checks)} divergencias={len(wrong)} linhas_dados={len(data_lines)} -> {'PASS' if passed else 'FAIL'}")
    for w in wrong:
        print(f"      DIVERGENCIA {w}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"prometheus_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "checks": len(checks), "wrong": len(wrong), "pass": passed})
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
