"""End-to-end API contract tests for Production Candidate V1 (TestClient; the live provider is always a stub)."""

import ast
import io
import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import observability
from app.geospatial import service as geo_service
from app.geospatial.schemas import Panchayat
from app.main import app
from app.weather import service as weather_service
from app.weather.providers import mock as mock_module
from cc_helpers import StubProvider, live_forecast, provider_error

client = TestClient(app, raise_server_exceptions=False)
BLOCK = "BLOCK-DEMO-001"
FRONTEND_DAILY = ("date", "temperature_min_c", "temperature_max_c", "rainfall_mm", "humidity_pct", "wind_kmph")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for v in ("WEATHER_PROVIDER", "WEATHER_FALLBACK", "WEATHER_CACHE_TTL_S", "WEATHER_FAILURE_COOLDOWN_S", "DOWNSCALING_METHOD"):
        monkeypatch.delenv(v, raising=False)
    weather_service.clear_state()
    observability.reset_counters()
    yield
    weather_service.clear_state()


def live(monkeypatch, **kw):
    stub = StubProvider(result=live_forecast(**kw) if kw else None)
    monkeypatch.setitem(weather_service._PROVIDERS, "open-meteo", stub)
    return stub


def failing(monkeypatch, kind="timeout"):
    stub = StubProvider(error=provider_error(kind, "simulated"))
    monkeypatch.setitem(weather_service._PROVIDERS, "open-meteo", stub)
    return stub


# ── health / readiness ─────────────────────────────────────────────────────────────────────────────────
def test_health_is_pure_liveness():
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"ok": True} and r.headers["x-request-id"]


def test_ready_reports_checks_and_does_not_depend_on_the_provider(monkeypatch):
    failing(monkeypatch)                                           # upstream is down...
    body = client.get("/ready").json()
    assert client.get("/ready").status_code == 200                 # ...and the service still reports ready
    assert body["ready"] is True and all(body["checks"].values())
    assert body["downscaling"]["active_method"] == "baseline" and body["downscaling"]["ml_correction_enabled"] is False
    assert body["weather"]["fallback_policy"] == "mock" and "disease_detection_models" in body


def test_ready_is_503_for_a_broken_local_configuration(monkeypatch):
    monkeypatch.setenv("WEATHER_PROVIDER", "no-such-provider")
    r = client.get("/ready")
    assert r.status_code == 503 and r.json()["ready"] is False and r.json()["checks"]["weather_provider_configured"] is False


# ── weather success + contract compatibility ───────────────────────────────────────────────────────────
def test_weather_success_path_keeps_frontend_fields_and_adds_provenance(monkeypatch):
    live(monkeypatch, n=3)
    r = client.get(f"/api/v1/weather/block/{BLOCK}/forecast?days=3")
    assert r.status_code == 200
    b = r.json()
    for k in ("latitude", "longitude", "elevation_m", "source", "is_mocked", "daily"):
        assert k in b
    assert b["source"] == "open-meteo" and b["is_mocked"] is False and b["data_origin"] == "live_provider"
    assert b["timezone"] == "Asia/Kolkata" and b["retrieved_at"] and b["fallback_reason"] is None and b["forecast_horizon_days"] == 3
    assert all(f in b["daily"][0] for f in FRONTEND_DAILY)


def test_downscaling_response_is_backward_compatible_and_answers_the_provenance_questions(monkeypatch):
    live(monkeypatch, n=2)
    b = client.get("/api/v1/downscaling/PANCH-DEMO-001/forecast?days=2").json()
    for k in ("panchayat_id", "panchayat_name", "block_id", "block_name", "method", "block_source", "adjustment", "daily"):
        assert k in b                                               # everything the frozen frontend reads
    assert b["method"] == "baseline" and b["model_version"] is None
    assert b["block_source"]["source"] == "open-meteo" and b["block_source"]["is_mocked"] is False
    p = b["provenance"]
    assert p["weather_source"] == "open-meteo" and p["data_origin"] == "live_provider"                 # 1. where from  2. real or mock
    assert p["retrieved_at"] and p["from_cache"] is False                                              # 3. when
    assert p["timezone"] == "Asia/Kolkata" and "Local calendar date" in p["day_definition"]            # 4. day definition
    assert p["correction_method"] == "baseline" and p["correction_status"] == "applied"                # 5. method
    assert p["elevation_available"] is True and p["panchayat_elevation_m"] == 1393.0                   # 6. elevation
    assert p["fallback_used"] is False and p["fallback_reason"] is None                                # 7. fallback
    assert p["ml_correction_enabled"] is False and p["research_data_used"] is False and p["model_version"] is None


def test_dates_agree_from_provider_to_panchayat_forecast(monkeypatch):
    live(monkeypatch, n=3, first="2026-10-05")
    b = client.get("/api/v1/downscaling/PANCH-DEMO-002/forecast?days=3").json()
    assert [d["date"] for d in b["daily"]] == [d["date"] for d in b["block_source"]["daily"]] == ["2026-10-05", "2026-10-06", "2026-10-07"]


def test_partial_forecast_flows_through_downscaling(monkeypatch):
    live(monkeypatch, n=5, requested_days=7, forecast_horizon_days=5, partial=True, omitted_dates=["2026-10-10", "2026-10-11"])
    b = client.get("/api/v1/downscaling/PANCH-DEMO-001/forecast?days=7").json()
    assert len(b["daily"]) == 5 and b["provenance"]["partial"] is True and b["provenance"]["omitted_dates"] == ["2026-10-10", "2026-10-11"]


# ── provider failure / fallback ────────────────────────────────────────────────────────────────────────
def test_fallback_is_explicit_in_weather_and_downscaling_responses(monkeypatch):
    failing(monkeypatch, "timeout")
    w = client.get(f"/api/v1/weather/block/{BLOCK}/forecast?days=3").json()
    assert w["is_mocked"] is True and w["source"] == "mock" and w["data_origin"] == "mock_fallback" and w["fallback_reason"].startswith("timeout")
    d = client.get("/api/v1/downscaling/PANCH-DEMO-003/forecast?days=3").json()
    assert d["block_source"]["is_mocked"] is True                   # field the frozen UI uses for its offline badge
    assert d["provenance"]["fallback_used"] is True and d["provenance"]["data_origin"] == "mock_fallback" and d["provenance"]["is_mocked"] is True


def test_provider_outage_is_503_when_fallback_is_disabled(monkeypatch):
    monkeypatch.setenv("WEATHER_FALLBACK", "error")
    failing(monkeypatch, "timeout")
    r = client.get(f"/api/v1/downscaling/block/{BLOCK}/forecast?days=3")
    assert r.status_code == 503 and r.headers["retry-after"]
    b = r.json()
    assert isinstance(b["detail"], str) and b["error"]["code"] == "weather_unavailable" and b["error"]["upstream_kind"] == "timeout" and b["error"]["request_id"]
    assert "Traceback" not in r.text and "simulated" not in r.text


def test_unusable_provider_response_is_502_when_fallback_is_disabled(monkeypatch):
    monkeypatch.setenv("WEATHER_FALLBACK", "error")
    failing(monkeypatch, "invalid_payload")
    r = client.get(f"/api/v1/weather/block/{BLOCK}/forecast")
    assert r.status_code == 502 and r.json()["error"]["code"] == "weather_upstream_invalid"


# ── error contract ─────────────────────────────────────────────────────────────────────────────────────
def test_unknown_ids_are_structured_404s():
    for url in ("/api/v1/weather/block/NOPE/forecast", "/api/v1/downscaling/NOPE/forecast", "/api/v1/downscaling/block/NOPE/forecast",
                "/api/v1/geospatial/blocks/NOPE", "/api/v1/geospatial/panchayats/NOPE", "/api/v1/no/such/route"):
        r = client.get(url)
        assert r.status_code == 404, url
        b = r.json()
        assert isinstance(b["detail"], str) and b["error"]["code"] == "not_found" and r.headers["x-request-id"] == b["error"]["request_id"]


def test_invalid_parameters_are_422_with_a_string_detail():
    for url in (f"/api/v1/weather/block/{BLOCK}/forecast?days=99", f"/api/v1/downscaling/PANCH-DEMO-001/forecast?days=0",
                f"/api/v1/downscaling/block/{BLOCK}/forecast?days=abc"):
        r = client.get(url)
        assert r.status_code == 422, url
        b = r.json()
        assert isinstance(b["detail"], str) and b["error"]["code"] == "invalid_request" and b["error"]["fields"][0]["field"] == "days"


def test_unexpected_failure_is_a_generic_500_without_internals(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("secret-internal-detail /srv/app.py line 42")
    monkeypatch.setattr(geo_service, "list_blocks", boom)
    r = client.get("/api/v1/geospatial/blocks")
    assert r.status_code == 500
    b = r.json()
    assert b["error"]["code"] == "internal_error" and "secret-internal-detail" not in r.text and "Traceback" not in r.text and r.headers["x-request-id"]


def test_wrong_method_is_a_structured_405():
    r = client.post(f"/api/v1/weather/block/{BLOCK}/forecast")
    assert r.status_code == 405 and r.json()["error"]["code"] == "method_not_allowed"


# ── downscaling robustness through the API ───────────────────────────────────────────────────────────────
def _patch_panchayat(monkeypatch, elevation):
    p = geo_service.get_panchayat("PANCH-DEMO-001")
    monkeypatch.setitem(geo_service._PANCHAYATS_BY_ID, "PANCH-DEMO-001", Panchayat(**{**p.model_dump(), "elevation_m": elevation}))


def test_missing_panchayat_elevation_keeps_block_values_and_says_so(monkeypatch):
    live(monkeypatch, n=2)
    _patch_panchayat(monkeypatch, None)
    b = client.get("/api/v1/downscaling/PANCH-DEMO-001/forecast?days=2").json()
    assert b["provenance"]["correction_status"] == "elevation_unavailable" and b["provenance"]["elevation_available"] is False
    assert b["adjustment"]["baseline_applied"] is False and b["adjustment"]["elevation_delta_m"] is None
    assert b["daily"] == b["block_source"]["daily"]                          # block value preserved, not invented
    assert b["provenance"]["data_origin"] == "live_provider"                   # weather WAS available: distinct from "weather unavailable"


def test_implausible_elevation_difference_is_not_applied(monkeypatch):
    live(monkeypatch, n=2)
    _patch_panchayat(monkeypatch, 8000.0)
    b = client.get("/api/v1/downscaling/PANCH-DEMO-001/forecast?days=2").json()
    assert b["provenance"]["correction_status"] == "elevation_delta_implausible" and b["daily"] == b["block_source"]["daily"]


def test_sea_level_block_elevation_zero_is_respected(monkeypatch):
    live(monkeypatch, n=1, elevation=0.0)
    b = client.get("/api/v1/downscaling/PANCH-DEMO-001/forecast?days=1").json()
    assert b["provenance"]["block_elevation_m"] == 0.0 and b["adjustment"]["elevation_delta_m"] == 1393.0


# ── ML stays disabled ────────────────────────────────────────────────────────────────────────────────────
def test_default_and_requested_ml_both_resolve_to_the_baseline(monkeypatch):
    live(monkeypatch, n=1)
    assert client.get("/api/v1/downscaling/PANCH-DEMO-001/forecast?days=1").json()["method"] == "baseline"
    monkeypatch.setenv("DOWNSCALING_METHOD", "ml_corrected")
    b = client.get("/api/v1/downscaling/PANCH-DEMO-001/forecast?days=1").json()
    assert b["method"] == "baseline" and b["provenance"]["ml_correction_enabled"] is False and b["model_version"] is None
    ready = client.get("/ready").json()
    assert ready["downscaling"]["active_method"] == "baseline" and "ml_corrected" in ready["downscaling"]["warning"]


def test_production_code_never_imports_research_or_loads_models_for_weather():
    root = Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            if any(n == "research" or n.startswith("research.") or n in ("joblib", "pickle") for n in names):
                offenders.append(str(path))
    assert not offenders


# ── timezone / day semantics ───────────────────────────────────────────────────────────────────────────
def test_mock_forecast_uses_the_local_ist_day_not_the_utc_day(monkeypatch):
    from datetime import datetime, timezone

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 4, 20, 0, tzinfo=timezone.utc).astimezone(tz) if tz else datetime(2026, 10, 4, 20, 0)

    monkeypatch.setattr(mock_module, "datetime", FrozenDatetime)
    monkeypatch.setenv("WEATHER_PROVIDER", "mock")
    b = client.get(f"/api/v1/weather/block/{BLOCK}/forecast?days=2").json()
    # 2026-10-04 20:00 UTC is already 2026-10-05 01:30 in Asia/Kolkata -> the first local day is the 5th.
    assert b["daily"][0]["date"] == "2026-10-05" and b["timezone"] == "Asia/Kolkata"


# ── observability ───────────────────────────────────────────────────────────────────────────────────────
def test_structured_logs_cover_the_operational_signals_without_leaking(monkeypatch):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(observability.JsonFormatter())
    observability.logger.addHandler(handler)
    try:
        failing(monkeypatch, "invalid_payload")
        client.get(f"/api/v1/downscaling/PANCH-DEMO-001/forecast?days=3&secret=hunter2")
        client.get("/health")
    finally:
        observability.logger.removeHandler(handler)
    lines = [json.loads(l) for l in stream.getvalue().splitlines()]
    events = {l["event"] for l in lines}
    assert {"invalid_weather_payload", "weather_provider_failure", "weather_fallback_used", "downscaling_baseline_used", "http_request"} <= events
    req = next(l for l in lines if l["event"] == "http_request")
    assert req["path"].startswith("/api/v1/downscaling") and req["status"] == 200 and "latency_ms" in req and req["request_id"]
    assert "hunter2" not in stream.getvalue()                                      # query strings are never logged
    assert not any(l.get("path") == "/health" for l in lines)                      # keep-alive pings are not logged
    counters = observability.counters()
    assert counters["weather_provider_failure"] >= 1 and counters["weather_fallback_used"] >= 1 and counters["downscaling_baseline_used"] >= 1
