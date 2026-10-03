"""Focused tests for the offline daily evaluation bridge (synthetic data only)."""

import numpy as np
import pandas as pd
import pytest

from daily_bridge import aggregate, baselines, config, decision, metrics, splits


def _hourly(day="2023-03-01", n=24, gp="G1"):
    h = np.arange(n)
    return pd.DataFrame({"gp_name": gp, config.DAY_COLUMN: day,
                         "temperature_c": 20.0 + h, "rainfall_mm": np.full(n, 0.5),
                         "relative_humidity_pct": np.linspace(40, 80, n), "wind_speed_kmph": np.arange(n, 0, -1, dtype=float)})


# ---- daily aggregation -----------------------------------------------------------------------------
def test_aggregation_rules_match_open_meteo_definitions():
    d = aggregate.to_daily(_hourly(), ["gp_name"]).iloc[0]
    assert d["temperature_max_c"] == 43.0 and d["temperature_min_c"] == 20.0      # max / min of hourly temperature
    assert d["rainfall_mm"] == pytest.approx(12.0)                                 # sum of 24 x 0.5 mm
    assert d["humidity_pct"] == pytest.approx(60.0)                                # mean of hourly RH
    assert d["wind_kmph"] == 24.0                                                  # max of hourly wind


def test_aggregation_table_documents_every_variable_with_units():
    table = {r["output_daily"]: r for r in aggregate.aggregation_table()}
    assert set(table) == set(config.DAILY_VARIABLES)
    assert table["rainfall_mm"]["unit"] == "mm" and table["wind_kmph"]["unit"] == "km/h"


# ---- missing data ------------------------------------------------------------------------------------
def test_incomplete_day_gives_nan_not_a_partial_statistic():
    h = _hourly(n=23)                                                              # one hour missing entirely
    d = aggregate.to_daily(h, ["gp_name"]).iloc[0]
    assert d[config.DAILY_VARIABLES].isna().all()


def test_nan_hour_invalidates_only_that_variable():
    h = _hourly()
    h.loc[3, "rainfall_mm"] = np.nan
    d = aggregate.to_daily(h, ["gp_name"]).iloc[0]
    assert np.isnan(d["rainfall_mm"]) and d["temperature_max_c"] == 43.0


def test_metrics_reject_nan_pairs_and_report_zero_samples():
    m = metrics.error_metrics([1, np.nan, 3], [1, 2, 5])
    assert m["n"] == 2 and m["mae"] == pytest.approx(1.0)
    assert metrics.error_metrics([np.nan], [1.0])["mae"] is None


# ---- metrics -----------------------------------------------------------------------------------------
def test_error_metrics_sign_convention_and_values():
    m = metrics.error_metrics([2.0, 4.0], [1.0, 1.0])                              # errors +1, +3 (pred - target)
    assert m == {"n": 2, "mae": 2.0, "rmse": pytest.approx(np.sqrt(5.0)), "bias": 2.0}


# ---- skill score -------------------------------------------------------------------------------------
def test_skill_definition_and_sign_labels():
    assert metrics.skill(0.5, 1.0) == pytest.approx(0.5)                           # half the error -> +0.5
    assert metrics.skill(1.0, 1.0) == 0.0
    assert metrics.skill(1.5, 1.0) == pytest.approx(-0.5)                          # worse than reference -> negative
    assert metrics.skill(1.0, 0.0) is None and metrics.skill(None, 1.0) is None
    assert metrics.skill_label(0.3) == "positive" and metrics.skill_label(-0.3) == "negative"
    assert metrics.skill_label(0.004) == "zero" and metrics.skill_label(None) == "undefined"


def test_bias_skill_uses_absolute_bias():
    cand, ref = {"mae": 1, "rmse": 1, "bias": -0.2}, {"mae": 1, "rmse": 1, "bias": 0.4}
    assert metrics.skill_scores(cand, ref)["abs_bias"] == pytest.approx(0.5)


def test_bootstrap_ci_brackets_a_clear_improvement():
    rng = np.random.default_rng(0)
    target = rng.normal(size=400)
    ref = target + rng.normal(scale=1.0, size=400)
    cand = target + rng.normal(scale=0.3, size=400)
    days = np.repeat(np.arange(100), 4)
    b = metrics.bootstrap_skill(days, cand, ref, target, reps=300, seed=1)
    assert b["mae"]["ci95"][0] > 0.4 and b["mae"]["ci95"][1] < 0.9


# ---- split integrity ---------------------------------------------------------------------------------
def _labels(rows):
    return pd.DataFrame(rows, columns=["gp_name", config.DAY_COLUMN, "label"])


def test_daily_labels_require_all_24_hours_to_agree():
    hours = pd.DataFrame({"gp_name": "G1", config.DAY_COLUMN: "2023-01-01", "fold": ["test"] * 23 + ["excluded"]})
    assert splits.daily_labels(hours, "fold")["label"].iloc[0] == "mixed"
    ok = pd.DataFrame({"gp_name": "G1", config.DAY_COLUMN: "2023-01-02", "fold": ["test"] * 24})
    assert splits.daily_labels(ok, "fold")["label"].iloc[0] == "test"


def test_split_audit_accepts_sound_fold_and_rejects_leakage():
    groups = {"A": "cg1", "B": "cg2"}
    sound = _labels([("A", "2022-06-01", "train"), ("B", "2023-06-01", "test")])
    assert splits.audit(sound, groups, "cg2")["cell_groups_disjoint"]
    with pytest.raises(ValueError, match="spatial leakage"):
        splits.audit(_labels([("B", "2022-06-01", "train"), ("B", "2023-06-01", "test")]), groups, "cg2")
    with pytest.raises(ValueError, match="temporal leakage"):
        splits.audit(_labels([("A", "2022-12-28", "train"), ("B", "2023-01-02", "test")]), groups, "cg2")
    with pytest.raises(ValueError, match="held-out"):
        splits.audit(_labels([("A", "2022-06-01", "train"), ("B", "2023-06-01", "test")]), groups, "cg1")


# ---- rainfall pass-through ---------------------------------------------------------------------------
def _evidence(**kw):
    base = {"pooled_mae_skill": 0.2, "pooled_rmse_skill": 0.2, "folds_mae_positive": 4, "quarters_mae_positive": 4,
            "ci_lower_mae_skill": 0.1, "mae_skill_vs_production": 0.3}
    base.update(kw)
    return base


def test_rainfall_stays_pass_through_unless_every_criterion_holds():
    assert decision.decide("rainfall_mm", _evidence())["decision"] == "CANDIDATE_MEETS_PROPOSED_EVIDENCE_RULE"
    for bad in ({"pooled_mae_skill": -0.1}, {"pooled_rmse_skill": 0.0}, {"folds_mae_positive": 2},
                {"quarters_mae_positive": 1}, {"ci_lower_mae_skill": -0.05}, {"mae_skill_vs_production": -0.2}):
        d = decision.decide("rainfall_mm", _evidence(**bad))
        assert d["decision"] == "KEEP_PASS_THROUGH" and d["rainfall_default_pass_through"] is True


def test_missing_evidence_never_passes():
    assert decision.decide("temperature_max_c", {})["decision"] == "KEEP_PASS_THROUGH"


def test_block_as_is_is_a_pass_through_and_production_baseline_is_the_live_function():
    block = pd.DataFrame({config.DAY_COLUMN: ["2023-01-01", "2023-01-02"], "temperature_max_c": [30.0, 31.0],
                          "temperature_min_c": [20.0, 21.0], "rainfall_mm": [0.0, 5.0], "humidity_pct": [60.0, 70.0],
                          "wind_kmph": [10.0, 12.0]})
    assert baselines.block_as_is(block).equals(block)
    same_elevation = baselines.production_baseline(block, 900.0, 900.0)             # delta 0 -> unchanged
    assert same_elevation["temperature_max_c"].tolist() == [30.0, 31.0] and same_elevation["rainfall_mm"].tolist() == [0.0, 5.0]
    higher = baselines.production_baseline(block, 900.0, 1400.0)                    # +500 m -> -3.25 C (lapse rate 0.0065)
    assert higher["temperature_max_c"].iloc[0] == pytest.approx(26.8, abs=0.06)


def test_constant_offset_diagnostic_is_train_only_and_a_pure_shift():
    train_t, train_b = [10.0, 12.0, np.nan], [9.0, 10.0, 5.0]
    out = baselines.constant_offset(train_t, train_b, [20.0, 30.0])                 # mean(target - block) = 1.5 over valid pairs
    assert out.tolist() == [21.5, 31.5]
