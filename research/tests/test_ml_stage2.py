"""
ML Stage 2 (research/ml_stage2/): Model C, fixed-config HistGradientBoosting.

Unit tests use a small synthetic long-format frame shaped like Phase 2D
(always run). Contract tests read the committed stage2_results.json; the
real-data recompute test needs the gitignored Parquet file.
"""

import json

import numpy as np
import pandas as pd
import pytest

from ml_stage2 import evaluation, features, model

FORBIDDEN_PHRASES = [
    "accurate panchayat weather", "observed panchayat weather", "ground truth",
    "validated panchayat forecast", "actual panchayat weather prediction",
]


def _synthetic(seed=0):
    rng = np.random.default_rng(seed)
    train_ts = pd.date_range("2021-03-01", periods=240, freq="h", tz="UTC")
    test_ts = pd.date_range("2023-03-01", periods=48, freq="h", tz="UTC")
    gps = [("G1", "cellA", 650.0, True), ("G2", "cellA", 700.0, True),
           ("G3", "cellB", 900.0, True), ("Agara", "cellA", 640.0, False)]
    rows = []
    for name, group, elev, primary in gps:
        for ts in list(train_ts) + list(test_ts):
            base = {v: rng.normal() for v in features.VARIABLES}
            for v in features.VARIABLES:
                coarse = 20 + base[v]
                rows.append({
                    "gp_name": name, "cell_group_id": group, "in_primary_population": primary,
                    "variable": v, "timestamp_utc": ts,
                    "coarse_bilinear_value": coarse, "coarse_nearest_value": coarse + 0.3,
                    "elevation_mean_m": elev, "elevation_range_m": elev / 10,
                    "centroid_to_cell_km": 3.0 if group == "cellA" else 5.0, "intersecting_cell_count": 2,
                    "target_value": coarse - 0.004 * (elev - 700) + 0.5 * np.sin(ts.hour) + rng.normal(scale=0.05),
                    "area_weighted_value": coarse + 1.0,
                    "target_cell_latitude": 12.1 if group == "cellA" else 12.0,
                    "target_cell_longitude": 77.0,
                })
    df = pd.DataFrame(rows)
    t = df["timestamp_utc"]
    role = np.where(~df["in_primary_population"], "excluded",
                    np.where((df["cell_group_id"] != "cellB") & (t < pd.Timestamp("2022-01-01", tz="UTC")), "train",
                             np.where((df["cell_group_id"] == "cellB") & (t >= pd.Timestamp("2023-01-01", tz="UTC")),
                                      "test", "excluded")))
    for k in range(1, 5):
        df[f"split_fold_{k}"] = role
    return df


def _c_preds(df, variable="temperature_c"):
    frame = features.build_feature_frame(df, variable)
    test, preds, _ = evaluation.fold_predictions(frame, "split_fold_1")
    return test, preds["C_hgb"]


# ---------------------------------------------------------------------
# Feature definition
# ---------------------------------------------------------------------

def test_feature_list_is_exactly_the_specified_set():
    assert features.FEATURES == [
        "era5_temperature_c", "era5_dewpoint_c", "era5_relative_humidity_pct", "era5_rainfall_mm",
        "era5_wind_speed_kmph", "elevation_mean_m", "elevation_range_m", "centroid_to_cell_km",
        "intersecting_cell_count", "sin_hour", "cos_hour", "sin_day_of_year", "cos_day_of_year",
    ]
    assert not set(features.FEATURES) & features.FORBIDDEN_FEATURES


def test_cyclic_time_features():
    ts = pd.Series(pd.to_datetime(["2021-01-01T00:00Z", "2021-01-01T06:00Z", "2024-12-31T12:00Z"], utc=True))
    tf = features.time_features(ts)
    assert tf.loc[0, "sin_hour"] == pytest.approx(0.0) and tf.loc[0, "cos_hour"] == pytest.approx(1.0)
    assert tf.loc[1, "sin_hour"] == pytest.approx(1.0)
    assert tf.loc[0, "sin_day_of_year"] == pytest.approx(0.0)
    assert np.allclose(tf["sin_hour"] ** 2 + tf["cos_hour"] ** 2, 1.0)
    # 2024 is a leap year: Dec 31 is day 366 -> angle just below 2*pi
    assert tf.loc[2, "cos_day_of_year"] == pytest.approx(np.cos(2 * np.pi * 365 / 366))


def test_coarse_features_come_from_all_five_coarse_variables_same_row_time():
    df = _synthetic()
    frame = features.build_feature_frame(df, "rainfall_mm")
    row = frame.iloc[5]
    src = df[(df["gp_name"] == row["gp_name"]) & (df["timestamp_utc"] == row["timestamp_utc"])]
    for v in features.VARIABLES:
        assert row[f"era5_{v}"] == src.loc[src["variable"] == v, "coarse_bilinear_value"].item()


# ---------------------------------------------------------------------
# 1-6. Leakage
# ---------------------------------------------------------------------

def test_1_target_values_do_not_enter_features():
    df = _synthetic()
    shifted = df.copy()
    shifted["target_value"] = shifted["target_value"] + 1000.0
    a = features.build_feature_frame(df, "temperature_c")[features.FEATURES]
    b = features.build_feature_frame(shifted, "temperature_c")[features.FEATURES]
    pd.testing.assert_frame_equal(a, b)
    assert "target_value" not in features.FEATURES


def test_2_area_weighted_value_does_not_enter_features():
    df = _synthetic()
    changed = df.copy()
    changed["area_weighted_value"] = -999.0
    pd.testing.assert_frame_equal(
        features.build_feature_frame(df, "dewpoint_c")[features.FEATURES],
        features.build_feature_frame(changed, "dewpoint_c")[features.FEATURES])
    assert "area_weighted_value" not in features.FEATURES


def test_3_target_cell_identity_does_not_enter_features():
    df = _synthetic()
    relabeled = df.copy()
    relabeled["cell_group_id"] = relabeled["cell_group_id"].map({"cellA": "P", "cellB": "Q"})
    relabeled["target_cell_latitude"] = 0.0
    relabeled["target_cell_longitude"] = 0.0
    _, a = _c_preds(df)
    _, b = _c_preds(relabeled)
    assert np.array_equal(a, b)
    for col in ("cell_group_id", "target_cell_latitude", "target_cell_longitude"):
        assert col not in features.FEATURES


def test_4_gp_identity_does_not_enter_features():
    df = _synthetic()
    renamed = df.copy()
    renamed["gp_name"] = renamed["gp_name"].map({"G1": "X1", "G2": "X2", "G3": "X3", "Agara": "Agara"})
    _, a = _c_preds(df)
    _, b = _c_preds(renamed)
    assert np.array_equal(a, b)
    assert "gp_name" not in features.FEATURES and "panchayat_lgd_code" not in features.FEATURES


def test_5_fold_assignment_does_not_enter_features():
    assert not any(f.startswith("split_fold") or f == "temporal_period" for f in features.FEATURES)
    df = _synthetic()
    other = df.copy()
    other["split_fold_2"] = "excluded"  # a fold column not being evaluated
    _, a = _c_preds(df)
    _, b = _c_preds(other)
    assert np.array_equal(a, b)


def test_6_no_future_data_enters_features():
    df = _synthetic()
    frame = features.build_feature_frame(df, "wind_speed_kmph")
    probe = frame.iloc[100]
    later = df.copy()
    future = later["timestamp_utc"] > probe["timestamp_utc"]
    later.loc[future, "coarse_bilinear_value"] = 1e6
    frame_later = features.build_feature_frame(later, "wind_speed_kmph")
    same = frame_later[(frame_later["gp_name"] == probe["gp_name"])
                       & (frame_later["timestamp_utc"] == probe["timestamp_utc"])].iloc[0]
    for f in features.FEATURES:
        assert same[f] == probe[f], f


# ---------------------------------------------------------------------
# 9. Preprocessing / binning fit on training rows only
# ---------------------------------------------------------------------

def test_9_tree_is_fit_only_on_training_rows(monkeypatch):
    df = _synthetic()
    frame = features.build_feature_frame(df, "temperature_c")
    seen = {}
    real_fit = evaluation.fit_tree

    def spy(X, y):
        seen["X"], seen["y"] = X, y
        return real_fit(X, y)

    monkeypatch.setattr(evaluation, "fit_tree", spy)
    evaluation.fold_predictions(frame, "split_fold_1")
    train = frame[frame["split_fold_1"] == "train"]
    assert len(seen["X"]) == len(train)
    assert np.array_equal(seen["X"], train[features.FEATURES].to_numpy(dtype=float))
    assert np.array_equal(seen["y"], train["target_value"].to_numpy(dtype=float))


def test_9_test_feature_values_do_not_change_fitted_model():
    df = _synthetic()
    frame = features.build_feature_frame(df, "temperature_c")
    train = frame[frame["split_fold_1"] == "train"]
    probe = train[features.FEATURES].to_numpy()[:50]
    m1 = model.fit_tree(train[features.FEATURES].to_numpy(), train["target_value"].to_numpy())
    altered = frame.copy()
    altered.loc[altered["split_fold_1"] == "test", features.FEATURES] *= 10
    train2 = altered[altered["split_fold_1"] == "train"]
    m2 = model.fit_tree(train2[features.FEATURES].to_numpy(), train2["target_value"].to_numpy())
    assert np.array_equal(model.predict_tree(m1, probe), model.predict_tree(m2, probe))


# ---------------------------------------------------------------------
# 10. Determinism + fixed configuration
# ---------------------------------------------------------------------

def test_10_fit_is_deterministic():
    _, a = _c_preds(_synthetic())
    _, b = _c_preds(_synthetic())
    assert np.array_equal(a, b)


def test_config_is_fixed_and_has_no_random_validation_split():
    assert model.CONFIG["early_stopping"] is False
    assert model.CONFIG["random_state"] == 0
    assert model.CONFIG["max_iter"] == 200 and model.CONFIG["min_samples_leaf"] == 200


# ---------------------------------------------------------------------
# Physical constraints are a separate diagnostic
# ---------------------------------------------------------------------

def test_constrain_and_invalid_counts():
    p = np.array([-1.0, 0.5, 120.0])
    assert evaluation.invalid_count("rainfall_mm", p) == 1
    assert evaluation.invalid_count("relative_humidity_pct", p) == 2
    assert evaluation.invalid_count("temperature_c", p) == 0
    assert list(evaluation.constrain("relative_humidity_pct", p)) == [0.0, 0.5, 100.0]
    assert list(evaluation.constrain("wind_speed_kmph", p)) == [0.0, 0.5, 120.0]
    assert list(evaluation.constrain("temperature_c", p)) == list(p)


def test_evaluate_refuses_mamballi_rows():
    df = _synthetic()
    df.loc[0, "gp_name"] = "Mamballi"
    with pytest.raises(RuntimeError):
        evaluation.evaluate(df, {"split_methodology": {"folds": []}, "rainfall_quality": {}})


# ---------------------------------------------------------------------
# Contract tests on the committed results
# ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def results():
    if not evaluation.RESULTS_PATH.exists():
        pytest.skip("stage2_results.json not generated")
    return json.loads(evaluation.RESULTS_PATH.read_text(encoding="utf-8"))


def test_7_temporal_gap_at_least_7_days(results):
    for fold in results["folds"].values():
        assert fold["leakage_audit"]["temporal_gap_at_least_7_days"]
        assert fold["leakage_audit"]["temporal_gap_hours"] >= 168


def test_8_spatial_groups_disjoint(results):
    held = set()
    for fold in results["folds"].values():
        a = fold["leakage_audit"]
        assert a["cell_groups_disjoint"]
        assert a["test_cell_groups"] == [fold["held_out_cell_group"]]
        held.add(fold["held_out_cell_group"])
    assert len(held) == 4
    assert results["effective_spatial_sample_size"] == "4 ERA5-Land spatial cell groups"


def test_agara_excluded_and_mamballi_unavailable(results):
    for fold in results["folds"].values():
        assert fold["leakage_audit"]["agara_rows_used"] == 0
        for v in features.VARIABLES:
            assert "Agara" not in fold["by_variable"][v]["test_gps"]
            assert "Mamballi" not in fold["by_variable"][v]["test_gps"]


def test_raw_results_are_primary_and_constrained_is_separate(results):
    for fold in results["folds"].values():
        for v in features.VARIABLES:
            block = fold["by_variable"][v]
            assert set(block["raw"]) == set(block["constrained_diagnostic"]) == set(evaluation.METHODS)
            for m in evaluation.METHODS:
                assert "invalid_predictions" in block["raw"][m]
                if block["raw"][m]["invalid_predictions"] == 0:
                    assert block["constrained_diagnostic"][m]["mae"] == pytest.approx(block["raw"][m]["mae"])
    assert "POST-PROCESSING DIAGNOSTIC ONLY" in results["constrained_diagnostic_note"]


def test_stage1_baselines_reproduced_exactly(results):
    stage1 = json.loads((evaluation._RESEARCH_DIR / "baselines" / "baseline_results.json").read_text(encoding="utf-8"))
    for f, fold in results["folds"].items():
        for v in features.VARIABLES:
            for m in ("A_bilinear", "A_nearest", "B_ridge"):
                for k in ("n", "mae", "rmse", "bias"):
                    assert fold["by_variable"][v]["raw"][m][k] == stage1["folds"][f]["by_variable"][v]["metrics"][m][k]


def test_statements_and_forbidden_phrases(results):
    assert results["evaluation_statement"] == "Evaluation against ERA5-Land reanalysis proxy — not observation."
    assert "do not establish generalized Panchayat-level forecasting skill" in results["spatial_sample_statement"]
    readme = (evaluation.RESULTS_PATH.parent / "README.md").read_text(encoding="utf-8").lower()
    text = json.dumps(results, ensure_ascii=False).lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in text and phrase not in readme, phrase


def test_10_real_fold_recompute_matches_committed_results(results):
    from multi_gp.build import DATASET_PATH

    if not DATASET_PATH.exists():
        pytest.skip("Phase 2D Parquet dataset not present locally")
    data = pd.read_parquet(DATASET_PATH, columns=evaluation.LOAD_COLUMNS)
    frame = features.build_feature_frame(data, "temperature_c")
    test, preds, _ = evaluation.fold_predictions(frame, "split_fold_2")
    fresh = evaluation.score("temperature_c", test, preds)
    stored = results["folds"]["split_fold_2"]["by_variable"]["temperature_c"]
    for m in evaluation.METHODS:
        for k in ("n", "mae", "rmse", "bias"):
            assert fresh["raw"][m][k] == pytest.approx(stored["raw"][m][k], rel=1e-12)
