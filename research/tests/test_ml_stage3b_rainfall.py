"""
ML Stage 3B two-stage rainfall model (research/ml_stage3b_rainfall/).

Unit tests use a small synthetic Phase-2D-shaped frame spanning 2021, 2022
and 2023 so the inner temporal split exists. Contract tests read the
committed rainfall_results.json.
"""

import json

import numpy as np
import pandas as pd
import pytest

from ml_stage2 import features as s2_features
from ml_stage3b_rainfall import config, evaluation, metrics, model

FORBIDDEN_PHRASES = [
    "accurate panchayat weather", "observed panchayat weather", "ground truth",
    "validated panchayat forecast", "actual panchayat weather prediction",
]


def _synthetic(seed=0):
    rng = np.random.default_rng(seed)
    ts = (list(pd.date_range("2021-03-01", periods=400, freq="h", tz="UTC"))
          + list(pd.date_range("2022-03-01", periods=400, freq="h", tz="UTC"))
          + list(pd.date_range("2023-03-01", periods=96, freq="h", tz="UTC")))
    gps = [("G1", "cellA", 650.0, True), ("G2", "cellA", 700.0, True),
           ("G3", "cellB", 900.0, True), ("Agara", "cellA", 640.0, False)]
    rain_by_time = {t: (rng.gamma(0.8, 1.0) if rng.random() < 0.3 else rng.uniform(0, 0.05)) for t in ts}
    rows = []
    for name, group, elev, primary in gps:
        for t in ts:
            coarse = {v: 20 + rng.normal() for v in s2_features.VARIABLES}
            coarse["rainfall_mm"] = rain_by_time[t]
            for v in s2_features.VARIABLES:
                c = coarse[v]
                target = max(0.0, 0.9 * c + rng.normal(scale=0.02)) if v == "rainfall_mm" else c + rng.normal()
                rows.append({
                    "gp_name": name, "cell_group_id": group, "in_primary_population": primary,
                    "variable": v, "timestamp_utc": t,
                    "coarse_bilinear_value": c, "coarse_nearest_value": c,
                    "elevation_mean_m": elev, "elevation_range_m": elev / 10,
                    "centroid_to_cell_km": 3.0, "intersecting_cell_count": 2,
                    "target_value": target, "area_weighted_value": target + 1.0,
                    "target_cell_latitude": 12.1, "target_cell_longitude": 77.0,
                })
    df = pd.DataFrame(rows)
    t = df["timestamp_utc"]
    role = np.where(~df["in_primary_population"], "excluded",
                    np.where((df["cell_group_id"] != "cellB") & (t < pd.Timestamp("2022-12-25", tz="UTC")), "train",
                             np.where((df["cell_group_id"] == "cellB") & (t >= pd.Timestamp("2023-01-01", tz="UTC")),
                                      "test", "excluded")))
    for k in range(1, 5):
        df[f"split_fold_{k}"] = role
    return df


def _frame(df):
    return s2_features.build_feature_frame(df, "rainfall_mm")


def _run(df):
    return evaluation.fold_predictions(_frame(df), "split_fold_1")


# ---------------------------------------------------------------------
# Pre-specified configuration
# ---------------------------------------------------------------------

def test_prespecified_settings():
    assert config.WET_THRESHOLD_MM == 0.1
    assert config.THRESHOLD_GRID[0] == 0.05 and config.THRESHOLD_GRID[-1] == 0.95 and len(config.THRESHOLD_GRID) == 19
    assert config.INNER_VAL_START - config.INNER_TRAIN_END_EXCLUSIVE == pd.Timedelta(days=7)
    for cfg in (config.CLASSIFIER_CONFIG, config.AMOUNT_CONFIG):
        assert cfg["early_stopping"] is False and cfg["random_state"] == 0
    assert config.AMOUNT_CONFIG["loss"] == "poisson"


def test_choose_threshold_tie_break_lowest():
    assert model.choose_threshold({0.3: 0.8, 0.4: 0.9, 0.5: 0.9, 0.6: 0.7}) == (0.4, 0.9)


# ---------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------

def test_occurrence_metrics_known_values():
    m = metrics.occurrence_metrics(np.array([1, 1, 0, 0], bool), np.array([1, 0, 1, 0], bool))
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (1, 1, 1, 1)
    assert m["precision"] == 0.5 and m["recall"] == 0.5 and m["f1"] == 0.5


def test_rainfall_metrics_zero_nonzero_behaviour():
    y = np.array([0.0, 0.05, 0.5, 2.0])
    pred = np.array([0.0, 0.0, 0.4, -0.1])
    m = metrics.rainfall_metrics(pred, y)
    assert m["overall"]["invalid_predictions"] == 1
    assert m["occurrence"]["tp"] == 1 and m["occurrence"]["fn"] == 1
    assert m["amount_on_observed_wet_hours"]["n"] == 2
    assert m["amount_on_hit_hours"]["n"] == 1
    assert m["dry_hour_behaviour"]["n_observed_dry"] == 2
    assert m["dry_hour_behaviour"]["fraction_predicted_exactly_zero"] == 1.0


# ---------------------------------------------------------------------
# Two-stage mechanics
# ---------------------------------------------------------------------

def test_amount_model_refuses_dry_rows():
    with pytest.raises(ValueError):
        model.fit_amount(np.zeros((300, 2)), np.full(300, 0.05))


def test_two_stage_output_is_zero_or_positive_amount():
    out = _run(_synthetic())
    s = out["raw"]["S_two_stage"]
    thr = out["fitted"]["selection"]["threshold"]
    assert (s[~out["classifier_wet"]] == 0.0).all()
    assert (s[out["classifier_wet"]] > 0.0).all()
    assert np.array_equal(out["classifier_wet"], out["prob"] >= thr)


def test_amount_model_trained_on_wet_training_rows_only(monkeypatch):
    frame = _frame(_synthetic())
    seen = {}
    real = model.fit_amount

    def spy(X, y):
        seen["y"] = np.asarray(y)
        return real(X, y)

    monkeypatch.setattr(model, "fit_amount", spy)
    evaluation.fold_predictions(frame, "split_fold_1")
    train = frame[frame["split_fold_1"] == "train"]
    assert (seen["y"] > config.WET_THRESHOLD_MM).all()
    assert len(seen["y"]) == int((train["target_value"] > config.WET_THRESHOLD_MM).sum())


# ---------------------------------------------------------------------
# Leakage / fold isolation
# ---------------------------------------------------------------------

def test_test_targets_do_not_affect_any_prediction_or_threshold():
    df = _synthetic()
    changed = df.copy()
    test_rows = changed["split_fold_1"] == "test"
    changed.loc[test_rows, "target_value"] = changed.loc[test_rows, "target_value"] * 7 + 3
    a, b = _run(df), _run(changed)
    assert a["fitted"]["selection"] == b["fitted"]["selection"]
    for m in evaluation.METHODS:
        assert np.array_equal(a["raw"][m], b["raw"][m])


def test_identity_and_derived_columns_do_not_affect_predictions():
    df = _synthetic()
    changed = df.copy()
    changed["area_weighted_value"] = -5.0
    changed["cell_group_id"] = changed["cell_group_id"].map({"cellA": "P", "cellB": "Q"})
    changed["gp_name"] = changed["gp_name"].map({"G1": "X1", "G2": "X2", "G3": "X3", "Agara": "Agara"})
    changed["target_cell_latitude"] = 0.0
    changed["split_fold_3"] = "excluded"
    a, b = _run(df), _run(changed)
    for m in evaluation.METHODS:
        assert np.array_equal(a["raw"][m], b["raw"][m])


def test_fit_receives_training_rows_only(monkeypatch):
    frame = _frame(_synthetic())
    seen = {}
    real = evaluation.fit_two_stage

    def spy(train):
        seen["train"] = train
        return real(train)

    monkeypatch.setattr(evaluation, "fit_two_stage", spy)
    evaluation.fold_predictions(frame, "split_fold_1")
    assert (seen["train"]["split_fold_1"] == "train").all()
    assert seen["train"]["timestamp_utc"].max() < pd.Timestamp("2022-12-25", tz="UTC")
    assert set(seen["train"]["cell_group_id"]) == {"cellA"}
    assert "Agara" not in set(seen["train"]["gp_name"])


def test_threshold_selection_uses_only_training_rows_with_inner_gap(monkeypatch):
    frame = _frame(_synthetic())
    seen = {}
    real = model.select_threshold

    def spy(train):
        seen["train"] = train
        return real(train)

    monkeypatch.setattr(model, "select_threshold", spy)
    evaluation.fold_predictions(frame, "split_fold_1")
    train = seen["train"]
    assert (train["split_fold_1"] == "train").all()
    inner_train, inner_val = model.inner_split(train)
    assert inner_train["timestamp_utc"].max() < config.INNER_TRAIN_END_EXCLUSIVE
    assert inner_val["timestamp_utc"].min() >= config.INNER_VAL_START
    assert inner_val["timestamp_utc"].min() - inner_train["timestamp_utc"].max() >= pd.Timedelta(days=7)
    assert inner_val["timestamp_utc"].max() < pd.Timestamp("2022-12-25", tz="UTC")


def test_selected_threshold_is_on_the_grid():
    sel = _run(_synthetic())["fitted"]["selection"]
    assert sel["threshold"] in config.THRESHOLD_GRID
    assert sel["inner_val_f1"] == max(sel["f1_curve"].values())


def test_evaluate_refuses_mamballi_rows():
    df = _synthetic()
    df.loc[0, "gp_name"] = "Mamballi"
    with pytest.raises(RuntimeError):
        evaluation.evaluate(df, {"split_methodology": {"folds": []}, "rainfall_quality": {}})


def test_deterministic():
    a, b = _run(_synthetic()), _run(_synthetic())
    assert a["fitted"]["selection"] == b["fitted"]["selection"]
    for m in evaluation.METHODS:
        assert np.array_equal(a["raw"][m], b["raw"][m])


# ---------------------------------------------------------------------
# Contract tests on the committed results
# ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def results():
    if not evaluation.RESULTS_PATH.exists():
        pytest.skip("rainfall_results.json not generated")
    return json.loads(evaluation.RESULTS_PATH.read_text(encoding="utf-8"))


def test_fold_isolation_and_gap(results):
    held = set()
    for fold in results["folds"].values():
        a = fold["leakage_audit"]
        assert a["cell_groups_disjoint"] and a["test_cell_groups"] == [fold["held_out_cell_group"]]
        assert a["temporal_gap_hours"] >= 168 and a["agara_rows_used"] == 0
        assert "Agara" not in fold["test_gps"] and "Mamballi" not in fold["test_gps"]
        held.add(fold["held_out_cell_group"])
    assert len(held) == 4


def test_threshold_selection_never_touched_test_period(results):
    assert results["threshold_selection_method"]["test_data_used"] is False
    for fold in results["folds"].values():
        ts = fold["threshold_selection"]
        assert all(v for k, v in ts["audit"].items() if k != "inner_gap_hours")
        assert ts["audit"]["inner_gap_hours"] == 168
        assert pd.Timestamp(ts["inner_val_range_utc"][1]) < pd.Timestamp("2022-12-25", tz="UTC")
        assert ts["threshold"] in config.THRESHOLD_GRID


def test_all_methods_scored_on_identical_rows(results):
    for block in [*results["folds"].values(), results["pooled"]]:
        for kind in ("raw", "constrained_diagnostic"):
            ns = {block[kind][m]["overall"]["n"] for m in evaluation.METHODS}
            assert len(ns) == 1
    for fold in results["folds"].values():
        assert fold["raw"]["A_bilinear"]["overall"]["n"] == fold["n_test_records"]


def test_raw_and_constrained_kept_separately(results):
    assert "POST-PROCESSING DIAGNOSTIC ONLY" in results["constrained_diagnostic_note"]
    for fold in results["folds"].values():
        for m in evaluation.METHODS:
            raw, con = fold["raw"][m]["overall"], fold["constrained_diagnostic"][m]["overall"]
            assert con["invalid_predictions"] == 0
            if raw["invalid_predictions"] == 0:
                assert raw["mae"] == con["mae"]
    assert results["fold_mean"]["raw"]["C4_hgb_regression"]["invalid_predictions_total"] > 0


def test_c4_rainfall_reproduces_stage2(results):
    assert results["c4_reproduction"]["exact_match"] and results["c4_reproduction"]["max_abs_difference"] == 0


def test_upstream_artifacts_unchanged_since_run(results):
    for name, path in evaluation.UPSTREAM_ARTIFACTS.items():
        assert evaluation.sha256(path) == results["upstream_artifact_sha256"][name], name


def test_results_written_only_inside_stage3b_module():
    assert evaluation.RESULTS_PATH.parent.name == "ml_stage3b_rainfall"
    assert evaluation.RESULTS_PATH.name == "rainfall_results.json"


def test_statements_and_forbidden_phrases(results):
    assert results["evaluation_statement"] == "Evaluation against ERA5-Land reanalysis proxy — not observation."
    assert "do not establish generalized Panchayat-level forecasting skill" in results["spatial_sample_statement"]
    readme = (evaluation.RESULTS_PATH.parent / "README.md").read_text(encoding="utf-8").lower()
    text = json.dumps(results, ensure_ascii=False).lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in text and phrase not in readme, phrase


def test_real_fold_recompute_matches_committed_results(results):
    from multi_gp.build import DATASET_PATH

    if not DATASET_PATH.exists():
        pytest.skip("Phase 2D Parquet dataset not present locally")
    data = pd.read_parquet(DATASET_PATH, columns=evaluation.LOAD_COLUMNS)
    frame = s2_features.build_feature_frame(data, "rainfall_mm")
    out = evaluation.fold_predictions(frame, "split_fold_2")
    fresh = metrics.rainfall_metrics(out["raw"]["S_two_stage"], out["test"]["target_value"].to_numpy())
    stored = results["folds"]["split_fold_2"]
    assert out["fitted"]["selection"]["threshold"] == stored["threshold_selection"]["threshold"]
    for k in ("n", "mae", "rmse", "bias"):
        assert fresh["overall"][k] == pytest.approx(stored["raw"]["S_two_stage"]["overall"][k], rel=1e-12)
