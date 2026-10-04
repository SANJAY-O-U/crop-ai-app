"""Edge cases of the deterministic baseline and the correction-strategy abstraction (equations unchanged)."""

import math

import pytest

from app.downscaling import baseline
from app.downscaling.baseline import (STATUS_APPLIED, STATUS_IMPLAUSIBLE, STATUS_INVALID, STATUS_UNAVAILABLE, apply_baseline,
                                       build_adjustment_metadata, classify_elevations)
from app.downscaling.strategy import REGISTRY, MLCorrectionStrategy, StrategyDisabledError, active_strategy, strategy_status
from cc_helpers import live_forecast


@pytest.mark.parametrize("block,pan,status", [
    (929.0, 1393.0, STATUS_APPLIED), (0.0, 100.0, STATUS_APPLIED), (3000.0, 0.0, STATUS_APPLIED),
    (None, 1000.0, STATUS_UNAVAILABLE), (900.0, None, STATUS_UNAVAILABLE), (None, None, STATUS_UNAVAILABLE),
    (float("nan"), 900.0, STATUS_INVALID), (900.0, float("inf"), STATUS_INVALID), (-9999.0, 900.0, STATUS_INVALID),
    (900.0, 99999.0, STATUS_INVALID), ("900", 900.0, STATUS_INVALID), (True, 900.0, STATUS_INVALID),
    (0.0, 4000.0, STATUS_IMPLAUSIBLE), (4000.0, 0.0, STATUS_IMPLAUSIBLE),
])
def test_elevation_classification(block, pan, status):
    assert classify_elevations(block, pan) == status


def test_every_unusable_elevation_case_returns_the_block_value_unchanged():
    f = live_forecast(n=2)
    for block, pan in ((None, 900.0), (float("nan"), 900.0), (0.0, 4500.0)):
        assert apply_baseline(f, block, pan) == list(f.daily)
        meta = build_adjustment_metadata(block, pan)
        assert meta["baseline_applied"] is False and meta["elevation_delta_m"] is None and meta["note"] and meta["status"] != STATUS_APPLIED


def test_applied_metadata_reports_status_and_the_unchanged_coefficients():
    meta = build_adjustment_metadata(929.0, 1393.0)
    assert meta["status"] == STATUS_APPLIED and meta["baseline_applied"] is True and meta["elevation_delta_m"] == 464.0
    assert meta["temperature_lapse_rate_c_per_m"] == 0.0065 and meta["coefficients_calibrated"] is False
    assert (baseline.RAINFALL_OROGRAPHIC_FACTOR_PER_100M, baseline.HUMIDITY_ADJUSTMENT_PCT_PER_100M, baseline.WIND_FACTOR_PER_100M) == (0.03, -0.5, 0.02)


def test_equations_are_unchanged_for_a_known_case():
    out = apply_baseline(live_forecast(n=1), 929.0, 1393.0)[0]        # delta +464 m on 20/30 C, 2 mm, 70 %, 10 km/h
    assert out.temperature_max_c == round(30.0 - 0.0065 * 464, 1) and out.temperature_min_c == round(20.0 - 0.0065 * 464, 1)
    assert out.rainfall_mm == round(2.0 * (1 + 0.03 * 4.64), 1) and out.humidity_pct == round(70.0 - 0.5 * 4.64, 1)
    assert out.wind_kmph == round(10.0 * (1 + 0.02 * 4.64), 1)


def test_outputs_stay_within_physical_bounds_at_the_largest_applied_delta():
    f = live_forecast(n=1, daily=live_forecast(n=1).daily)
    for pan in (3000.0, 0.0):
        d = apply_baseline(f, 0.0 if pan == 3000.0 else 3000.0, pan)[0]
        assert d.rainfall_mm >= 0 and 0 <= d.humidity_pct <= 100 and d.wind_kmph >= 0 and not math.isnan(d.temperature_max_c)


def test_baseline_is_deterministic():
    f = live_forecast(n=3)
    assert apply_baseline(f, 929.0, 741.0) == apply_baseline(f, 929.0, 741.0)


# ── correction strategy abstraction ─────────────────────────────────────────────────────────────────────
def test_default_active_strategy_is_the_baseline(monkeypatch):
    monkeypatch.delenv("DOWNSCALING_METHOD", raising=False)
    s = active_strategy()
    assert s.method == "baseline" and s.enabled
    r = s.correct(live_forecast(n=1), 929.0, 1393.0)
    assert r.method == "baseline" and r.model_version is None and r.status == STATUS_APPLIED


@pytest.mark.parametrize("requested", ["ml_corrected", "ML_CORRECTED", "gradient-boost", "", "  "])
def test_ml_and_unknown_methods_can_never_become_active(monkeypatch, requested):
    monkeypatch.setenv("DOWNSCALING_METHOD", requested)
    assert active_strategy().method == "baseline"
    assert strategy_status()["ml_correction_enabled"] is False and strategy_status()["active_method"] == "baseline"


def test_ml_strategy_is_a_disabled_placeholder_with_no_model():
    ml = REGISTRY["ml_corrected"]
    assert isinstance(ml, MLCorrectionStrategy) and ml.enabled is False
    with pytest.raises(StrategyDisabledError):
        ml.correct(live_forecast(n=1), 929.0, 1393.0)
    assert not hasattr(ml, "model") and not hasattr(ml, "predict")
