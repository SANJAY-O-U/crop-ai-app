from datetime import date

from app.downscaling.baseline import (
    TEMPERATURE_LAPSE_RATE_C_PER_M,
    apply_baseline,
    build_adjustment_metadata,
)
from app.weather.schemas import DailyWeather, PointForecast

_BLOCK_FORECAST = PointForecast(
    latitude=13.40, longitude=77.73, elevation_m=929.0,
    source="open-meteo", is_mocked=False,
    daily=[DailyWeather(
        date=date(2026, 1, 1),
        temperature_min_c=20.0, temperature_max_c=27.0,
        rainfall_mm=15.0, humidity_pct=80.0, wind_kmph=17.0,
    )],
)


def test_higher_elevation_panchayat_is_cooler():
    # +464m, matching the real Panchayat A seed delta
    daily = apply_baseline(_BLOCK_FORECAST, block_elevation_m=929.0, panchayat_elevation_m=1393.0)
    expected_shift = -TEMPERATURE_LAPSE_RATE_C_PER_M * 464
    assert daily[0].temperature_max_c == round(27.0 + expected_shift, 1)
    assert daily[0].temperature_max_c < 27.0


def test_lower_elevation_panchayat_is_warmer():
    daily = apply_baseline(_BLOCK_FORECAST, block_elevation_m=929.0, panchayat_elevation_m=741.0)
    assert daily[0].temperature_max_c > 27.0


def test_zero_delta_returns_block_value_unchanged():
    daily = apply_baseline(_BLOCK_FORECAST, block_elevation_m=900.0, panchayat_elevation_m=900.0)
    assert daily[0].temperature_max_c == 27.0
    assert daily[0].rainfall_mm == 15.0


def test_missing_elevation_falls_back_to_block_value_unmodified():
    daily = apply_baseline(_BLOCK_FORECAST, block_elevation_m=None, panchayat_elevation_m=1200.0)
    assert daily[0].temperature_max_c == 27.0
    assert daily[0].rainfall_mm == 15.0


def test_rainfall_never_goes_negative_at_extreme_negative_delta():
    daily = apply_baseline(_BLOCK_FORECAST, block_elevation_m=3000.0, panchayat_elevation_m=0.0)
    assert daily[0].rainfall_mm >= 0
    assert daily[0].humidity_pct >= 0
    assert daily[0].wind_kmph >= 0


def test_adjustment_metadata_reports_delta_and_marks_uncalibrated():
    meta = build_adjustment_metadata(929.0, 1393.0)
    assert meta["elevation_delta_m"] == 464.0
    assert meta["coefficients_calibrated"] is False


def test_adjustment_metadata_handles_missing_elevation():
    meta = build_adjustment_metadata(None, 1393.0)
    assert meta["elevation_delta_m"] is None
    assert "note" in meta
