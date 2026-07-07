"""G3 — rótulo de fonte: live/eval/estimate corretos; ARMADILHA projeção != live."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from obs_svc.aggregator import Aggregator  # noqa: E402
from obs_svc.model import Source  # noqa: E402
from obs_svc.scraper import FakeScraper  # noqa: E402
from obs_svc.upstreams import Upstream  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"

UPS = [Upstream("inf", "http://inf/metrics")]
PAYLOADS = {"inf": {"source": "live", "tokens_input_total": 100, "tokens_output_total": 50}}


def main() -> int:
    checks: list[tuple[str, bool]] = []
    agg = Aggregator(UPS, FakeScraper(PAYLOADS))
    agg.refresh()

    # Ingest de eval carrega dataset_date e vira source=eval.
    agg.ingest_eval("inf", "2026-07-04", [{"name": "faithfulness", "value": 0.975}])

    by_source: dict[str, list] = {"live": [], "eval": [], "estimate": []}
    for m in agg.overview():
        by_source[str(m.source)].append(m)

    checks.append(("live_from_scrape", any(m.name == "tokens_input_total" for m in by_source["live"])))
    checks.append(("eval_from_ingest", any(m.name == "faithfulness" for m in by_source["eval"])))
    checks.append(("eval_has_date", all(m.ts == "2026-07-04" for m in by_source["eval"])))

    # ARMADILHA: derivado (projeção agregada) DEVE ser estimate, nunca live.
    derived = [m for m in by_source["estimate"] if m.name == "ecosystem_tokens_total"]
    checks.append(("derived_is_estimate", len(derived) == 1 and derived[0].value == 150.0))
    live_names = {m.name for m in by_source["live"]}
    checks.append(("derived_not_live", "ecosystem_tokens_total" not in live_names))
    checks.append(("no_source_leak", all(m.source in Source for m in agg.overview())))

    wrong = [n for n, ok in checks if not ok]
    passed = not wrong
    print(f"[G3] checks={len(checks)} divergencias={len(wrong)} -> {'PASS' if passed else 'FAIL'}")
    for w in wrong:
        print(f"      DIVERGENCIA {w}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"source_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "checks": len(checks), "wrong": len(wrong), "pass": passed})
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
