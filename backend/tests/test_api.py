"""
API-level structure tests via FastAPI's TestClient.

WEATHER_PROVIDER is forced to "mock" for these tests so they never depend on
network access — the real Open-Meteo path is covered separately in
test_weather_provider.py.
"""

import os

os.environ["WEATHER_PROVIDER"] = "mock"

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# ── Existing CropAI endpoints — must keep working untouched ───────────────────

def test_existing_health_endpoint_untouched():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_existing_cropai_health_endpoint_untouched():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_existing_cropai_crops_endpoint_untouched():
    resp = client.get("/api/crops")
    assert resp.status_code == 200
    body = resp.json()
    assert "tomato" in body
    assert "wheat" not in body  # confirms the known Phase-1-untouched wheat gap


# ── New CropCast geospatial endpoints ──────────────────────────────────────────

def test_geospatial_list_panchayats():
    resp = client.get("/api/v1/geospatial/panchayats")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 3
    assert all(p["is_demo_data"] for p in body)


def test_geospatial_unknown_panchayat_404():
    resp = client.get("/api/v1/geospatial/panchayats/DOES-NOT-EXIST")
    assert resp.status_code == 404


# ── New CropCast weather endpoint ──────────────────────────────────────────────

def test_weather_block_forecast_shape():
    resp = client.get("/api/v1/weather/block/BLOCK-DEMO-001/forecast?days=3")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "mock"
    assert body["is_mocked"] is True
    assert len(body["daily"]) == 3
    for field in ("date", "temperature_min_c", "temperature_max_c", "rainfall_mm", "humidity_pct", "wind_kmph"):
        assert field in body["daily"][0]


def test_weather_unknown_block_404():
    resp = client.get("/api/v1/weather/block/DOES-NOT-EXIST/forecast")
    assert resp.status_code == 404


# ── New CropCast downscaling endpoint ──────────────────────────────────────────

def test_downscaling_single_panchayat_response_shape():
    resp = client.get("/api/v1/downscaling/PANCH-DEMO-001/forecast?days=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["method"] == "baseline"
    assert body["panchayat_id"] == "PANCH-DEMO-001"
    assert "block_source" in body
    assert "adjustment" in body
    assert len(body["daily"]) == 2


def test_downscaling_unknown_panchayat_404():
    resp = client.get("/api/v1/downscaling/DOES-NOT-EXIST/forecast")
    assert resp.status_code == 404


def test_downscaling_block_returns_all_panchayats_with_distinct_values():
    resp = client.get("/api/v1/downscaling/block/BLOCK-DEMO-001/forecast?days=1")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 3
    # Different elevations must not all collapse to an identical adjustment.
    deltas = {entry["adjustment"]["elevation_delta_m"] for entry in body}
    assert len(deltas) == 3
