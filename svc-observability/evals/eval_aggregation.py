"""G2 — agregação: funde upstreams; serviço fora → parcial + stale (determinístico)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from obs_svc.aggregator import Aggregator  # noqa: E402
from obs_svc.scraper import FakeScraper  # noqa: E402
from obs_svc.upstreams import Upstream  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"

UPS = [Upstream("a", "http://a/metrics"), Upstream("b", "http://b/metrics"), Upstream("c", "http://c/metrics")]
PAYLOADS = {
    "a": {"source": "live", "requests_total": 10, "latency_ms_p95": 5.0},
    "b": {"source": "live", "requests_total": 20, "by_layer": {"semantic": 3, "llm": 1}},
    "c": {"source": "live", "searches_total": 7},
}


def main() -> int:
    checks: list[tuple[str, bool]] = []

    # Todos no ar.
    agg = Aggregator(UPS, FakeScraper(PAYLOADS))
    ok, failed = agg.refresh()
    checks.append(("all_up", ok == 3 and failed == 0))
    ov = agg.overview()
    names = {(m.service, m.name): m.value for m in ov}
    checks.append(("merge_a", names.get(("a", "requests_total")) == 10.0))
    checks.append(("merge_b_nested", names.get(("b", "by_layer_semantic")) == 3.0))
    checks.append(("merge_c", names.get(("c", "searches_total")) == 7.0))

    # Um fora → parcial + stale nas suas métricas antigas.
    agg2 = Aggregator(UPS, FakeScraper(PAYLOADS, fail={"b"}))
    agg2.refresh()  # 1ª: b já falha (sem cache) → 0 métricas de b
    ok2, failed2 = agg2.refresh()
    checks.append(("partial_failed", failed2 == 1))
    checks.append(("others_ok", ok2 == 2))
    # a e c continuam presentes
    services_ok = {s.name: s.ok for s in agg2.services()}
    checks.append(("b_down_a_c_up", services_ok == {"a": True, "b": False, "c": True}))

    # Stale: com cache prévio, b fora mantém métricas marcadas stale.
    agg3 = Aggregator(UPS, FakeScraper(PAYLOADS))
    agg3.refresh()  # popula cache
    agg3._scraper = FakeScraper(PAYLOADS, fail={"b"})  # b cai
    agg3.refresh()
    b_metrics = [m for m in agg3.overview() if m.service == "b"]
    checks.append(("b_stale", bool(b_metrics) and all(m.stale for m in b_metrics)))

    wrong = [n for n, ok in checks if not ok]
    passed = not wrong
    print(f"[G2] checks={len(checks)} divergencias={len(wrong)} -> {'PASS' if passed else 'FAIL'}")
    for w in wrong:
        print(f"      DIVERGENCIA {w}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"aggregation_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "checks": len(checks), "wrong": len(wrong), "pass": passed})
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
