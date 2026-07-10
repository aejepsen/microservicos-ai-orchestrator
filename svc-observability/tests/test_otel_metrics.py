"""G-OTLP — export OTLP de métricas agregadas (D7): opt-in, fiel à fonte, fail-open."""

from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import PAYLOADS
from obs_svc import otel_metrics
from obs_svc.app import State, create_app
from obs_svc.config import Settings
from obs_svc.scraper import FakeScraper


def _settings(**kw) -> Settings:
    return Settings(
        internal_key="test-key", allow_local_upstream=True,
        rate_limit_per_min=100000, **kw,
    )


def _collect(reader) -> dict[str, list[tuple[float, dict]]]:
    found: dict[str, list[tuple[float, dict]]] = {}
    data = reader.get_metrics_data()
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                for dp in metric.data.data_points:
                    found.setdefault(metric.name, []).append(
                        (dp.value, dict(dp.attributes))
                    )
    return found


def test_desligado_por_default() -> None:
    """G-OTLP-1: sem OTLP_METRICS_ENABLED → no-op absoluto."""
    st = State(_settings(), FakeScraper(PAYLOADS))
    assert otel_metrics.init_metrics_export(st.agg, st.settings) is None


def test_export_reflete_agregado_com_fonte() -> None:
    """G-OTLP-2: valores e atributos (service/source/stale) idênticos ao overview."""
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    st = State(_settings(otlp_metrics_enabled=True), FakeScraper(PAYLOADS))
    st.agg.refresh()
    reader = InMemoryMetricReader()
    export = otel_metrics.init_metrics_export(st.agg, st.settings, reader=reader)
    assert export is not None
    assert export.sync() == 0  # init já registrou tudo que o overview tem

    found = _collect(reader)
    # live raspado preserva valor e origem
    routes = [p for p in found["routes_total"] if p[1]["service"] == "svc-router"]
    assert routes and routes[0][0] == 9 and routes[0][1]["source"] == "live"
    # derivado NUNCA vira live no export (armadilha do G3 vale aqui também)
    estimates = [
        attrs for pts in found.values() for _, attrs in pts
        if attrs["source"] == "estimate"
    ]
    assert estimates, "derivados devem ser exportados com source=estimate"
    # métrica inédita pós-registro (eval) entra após sync()
    st.agg.ingest_eval("svc-rag", "2026-07-10", [{"name": "hit_at_5", "value": 0.982}])
    assert export.sync() == 1
    assert "hit_at_5" in _collect(reader)


def test_fail_open_saas_fora(monkeypatch) -> None:
    """G-OTLP-3: endpoint morto não derruba init, refresh nem API."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "1")
    settings = _settings(otlp_metrics_enabled=True, otlp_metrics_interval_s=0.05)
    st = State(settings, FakeScraper(PAYLOADS))
    client = TestClient(create_app(settings=settings, state=st))
    r = client.post("/v1/refresh", headers={"X-Internal-Key": "test-key"})
    assert r.status_code == 200
    r = client.get("/v1/overview", headers={"X-Internal-Key": "test-key"})
    assert r.status_code == 200
    assert st.metrics_export is not None
    st.metrics_export.close()  # flush final não pode propagar erro (D7)
