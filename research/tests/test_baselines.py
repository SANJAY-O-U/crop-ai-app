"""
ML Stage 1 baselines (research/baselines/).

Unit tests use small synthetic frames (always run). Contract tests read the
committed baseline_results.json; the recompute test also needs the
gitignored Phase 2D Parquet file and is skipped where it is absent.
"""

import json

import numpy as np
import pandas as pd
import pytest

from baselines import baseline, evaluation
from baselines.metrics import error_metrics

FORBIDDEN_PHRASES = [
    "accurate panchayat weather", "observed panchayat weather", "ground truth",
    "validated panchayat forecast", "actual panchayat weather prediction",
]


# ---------------------------------------------------------------------
# Synthetic fixture shaped like the Phase 2D dataset
# ---------------------------------------------------------------------

def _synthetic(seed=0, test_target_offset=0.0, test_feature_scale=1.0):
    rng = np.random.default_rng(seed)
    train_ts = pd.date_range("2021-01-01", periods=48, freq="h", tz="UTC")
    test_ts = pd.date_range("2023-01-01", periods=24, freq="h", tz="UTC")
    gps = [("G1", "cellA", 650.0, True), ("G2", "cellA", 700.0, True),
           ("G3", "cellB", 900.0, True), ("Agara", "cellA", 640.0, False)]
    rows = []
    for name, group, elev, primary in gps:
        for ts in list(train_ts) + list(test_ts):
            coarse = 25 + rng.normal()
            is_test_time = ts >= pd.Timestamp("2023-01-01", tz="UTC")
            target = coarse - 0.005 * (elev - 700) + rng.normal(scale=0.1)
            rows.append({
                "gp_name": name, "cell_group_id": group, "in_primary_population": primary,
                "coverage_status": "COMPLETE" if primary else "PARTIAL", "variable": "temperature_c",
                "timestamp_utc": ts, "coarse_bilinear_value": coarse * (test_feature_scale if is_test_time else 1.0),
                "coarse_nearest_value": coarse + 0.5, "elevation_mean_m": elev,
                "elevation_range_m": elev / 10, "centroid_to_cell_km": 3.0, "intersecting_cell_count": 2,
                "target_value": target + (test_target_offset if is_test_time else 0.0),
            })
    df = pd.DataFrame(rows)
    t = df["timestamp_utc"]
    df["split_fold_1"] = np.where(~df["in_primary_population"], "excluded",
                                  np.where((df["cell_group_id"] != "cellB") & (t < "2022-01-01"), "train",
                                           np.where((df["cell_group_id"] == "cellB") & (t >= "2023-01-01"), "test", "excluded")))
    return df


# ---------------------------------------------------------------------
# Metrics / ridge correctness
# ---------------------------------------------------------------------

def test_error_metrics_known_values():
    m = error_metrics([1.0, 3.0], [2.0, 2.0])
    assert m == {"n": 2, "mae": 1.0, "rmse": 1.0, "bias": 0.0}
    assert error_metrics([3.0], [1.0])["bias"] == 2.0  # prediction - target


def test_error_metrics_rejects_nan():
    with pytest.raises(ValueError):
        error_metrics([1.0, np.nan], [1.0, 1.0])


def test_ridge_recovers_linear_relationship():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(5000, 5))
    y = 2.0 + X @ np.array([1.5, -0.5, 0.0, 0.25, 0.0])
    model = baseline.fit_ridge(X, y, alpha=1e-9)
    assert np.allclose(baseline.predict_ridge(model, X), y, atol=1e-6)


def test_zero_variance_feature_is_neutralized():
    X = np.column_stack([np.arange(10.0), np.full(10, 7.0)])
    model = baseline.fit_ridge(X, 2 * np.arange(10.0))
    assert model["coef_standardized"][1] == 0.0


# ---------------------------------------------------------------------
# 1 + 2. No target leakage, no target-cell identity leakage
# ---------------------------------------------------------------------

def test_features_exclude_target_and_target_cell_identity():
    assert not set(baseline.FEATURES) & baseline.FORBIDDEN_FEATURES
    for col in ("target_value", "area_weighted_value", "cell_group_id",
                "target_cell_latitude", "target_cell_longitude"):
        assert col not in baseline.FEATURES
    assert baseline.FEATURES == [
        "coarse_bilinear_value", "elevation_mean_m", "elevation_range_m",
        "centroid_to_cell_km", "intersecting_cell_count",
    ]


def test_predictions_do_not_depend_on_test_targets():
    a = evaluation.evaluate_fold_variable(_synthetic(), "split_fold_1", "temperature_c")
    b = evaluation.evaluate_fold_variable(_synthetic(test_target_offset=100.0), "split_fold_1", "temperature_c")
    assert a["B_ridge_model"] == b["B_ridge_model"]
    # metrics change (targets moved) but the fitted model does not
    assert a["metrics"]["B_ridge"]["mae"] != b["metrics"]["B_ridge"]["mae"]


def test_cell_group_labels_do_not_affect_predictions():
    df = _synthetic()
    relabeled = df.copy()
    relabeled["cell_group_id"] = relabeled["cell_group_id"].map({"cellA": "X", "cellB": "Y"})
    a = evaluation.evaluate_fold_variable(df, "split_fold_1", "temperature_c")
    b = evaluation.evaluate_fold_variable(relabeled, "split_fold_1", "temperature_c")
    assert a["metrics"] == b["metrics"]


# ---------------------------------------------------------------------
# 3. Preprocessing fit only on training rows
# ---------------------------------------------------------------------

def test_standardizer_fit_only_on_training_rows():
    df = _synthetic()
    res = evaluation.evaluate_fold_variable(df, "split_fold_1", "temperature_c")
    train = df[(df["split_fold_1"] == "train") & (df["variable"] == "temperature_c")]
    for f in baseline.FEATURES:
        assert res["B_ridge_model"]["training_feature_mean"][f] == pytest.approx(train[f].mean())
        std = train[f].std(ddof=0)
        assert res["B_ridge_model"]["training_feature_std"][f] == pytest.approx(std if std > 0 else 1.0)
    assert res["B_ridge_model"]["n_train"] == len(train)


def test_scaling_test_features_does_not_change_fitted_model():
    a = evaluation.evaluate_fold_variable(_synthetic(), "split_fold_1", "temperature_c")
    b = evaluation.evaluate_fold_variable(_synthetic(test_feature_scale=10.0), "split_fold_1", "temperature_c")
    assert a["B_ridge_model"] == b["B_ridge_model"]


# ---------------------------------------------------------------------
# 7. Mamballi unavailable
# ---------------------------------------------------------------------

def test_evaluate_refuses_mamballi_rows():
    df = _synthetic()
    df.loc[0, "gp_name"] = "Mamballi"
    with pytest.raises(RuntimeError):
        evaluation.evaluate(df, {"split_methodology": {"folds": []}, "rainfall_quality": {}})


# ---------------------------------------------------------------------
# 9. Determinism
# ---------------------------------------------------------------------

def test_fit_is_deterministic():
    a = evaluation.evaluate_fold_variable(_synthetic(), "split_fold_1", "temperature_c")
    b = evaluation.evaluate_fold_variable(_synthetic(), "split_fold_1", "temperature_c")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ---------------------------------------------------------------------
# Contract tests on the committed results JSON
# ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def results():
    if not evaluation.RESULTS_PATH.exists():
        pytest.skip("baseline_results.json not generated")
    return json.loads(evaluation.RESULTS_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest():
    from multi_gp.build import MANIFEST_PATH

    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_results_cover_every_fold_and_variable(results):
    assert set(results["folds"]) == set(evaluation.FOLD_COLUMNS)
    assert results["variables"] == evaluation.VARIABLES
    for fold in results["folds"].values():
        for v in evaluation.VARIABLES:
            for method in evaluation.METHODS:
                m = fold["by_variable"][v]["metrics"][method]
                assert m["n"] > 0 and m["mae"] is not None and m["rmse"] >= m["mae"]


# 4. Spatial groups separated
def test_spatial_groups_separated(results):
    held_out = set()
    for fold in results["folds"].values():
        audit = fold["leakage_audit"]
        assert audit["cell_groups_disjoint"]
        assert audit["test_cell_groups"] == [fold["held_out_cell_group"]]
        assert fold["held_out_cell_group"] not in audit["train_cell_groups"]
        held_out.add(fold["held_out_cell_group"])
    assert len(held_out) == 4
    assert results["effective_spatial_sample_size"] == "4 ERA5-Land spatial cell groups"


# 5. Temporal gap preserved
def test_temporal_gap_preserved(results):
    for fold in results["folds"].values():
        audit = fold["leakage_audit"]
        assert audit["temporal_gap_at_least_7_days"]
        assert audit["temporal_gap_hours"] >= 7 * 24
        assert pd.Timestamp(audit["test_first_timestamp_utc"]).year == 2023


# 6. Agara excluded from primary metrics
def test_agara_excluded(results):
    assert "Agara" not in results["population"]["primary_gps"]
    for fold in results["folds"].values():
        assert fold["leakage_audit"]["agara_rows_used"] == 0
        assert fold["leakage_audit"]["partial_or_nonprimary_rows_used"] == 0
        for v in evaluation.VARIABLES:
            assert "Agara" not in fold["by_variable"][v]["test_gps"]


# 7. Mamballi unavailable
def test_mamballi_unavailable(results):
    assert "Mamballi" not in results["population"]["primary_gps"]
    assert "UNAVAILABLE" in results["population"]["mamballi"]


# 8. Rainfall handling preserved
def test_rainfall_handling_preserved(results, manifest):
    rain, rq = results["rainfall"], manifest["rainfall_quality"]
    assert rain["missing_first_hour_rows"] == rq["target_missing_rows"] == 11
    assert rain["missing_first_hour_rows_used_in_any_fold"] == 0
    assert rain["tiny_negative_steps_clamped_target_rows"] == rq["target_rainfall_clamped_rows"]
    assert rain["max_abs_clamped_step_mm"] == rq["max_abs_clamped_step_mm"] < 1e-3
    for fold in results["folds"].values():
        assert fold["leakage_audit"]["missing_target_rows_used"] == 0


def test_required_statements_present_and_forbidden_phrases_absent(results):
    assert results["evaluation_statement"] == "Evaluation against ERA5-Land reanalysis proxy — not observation."
    assert "4 ERA5-Land cell groups" in results["spatial_sample_statement"]
    assert "do not establish generalized Panchayat-level forecasting skill" in results["spatial_sample_statement"]
    text = json.dumps(results, ensure_ascii=False).lower()
    readme = (evaluation.RESULTS_PATH.parent / "README.md").read_text(encoding="utf-8").lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in text, phrase
        assert phrase not in readme, phrase


def test_results_json_matches_dataset_manifest(results, manifest):
    assert results["dataset"]["sha256"] == manifest["dataset_file_sha256"]
    assert results["dataset"]["row_count"] == manifest["row_count"]


# 9. Determinism on the real data: recompute one fold x variable
def test_real_fold_recompute_matches_committed_results(results):
    from multi_gp.build import DATASET_PATH

    if not DATASET_PATH.exists():
        pytest.skip("Phase 2D Parquet dataset not present locally")
    data = pd.read_parquet(DATASET_PATH, columns=evaluation.LOAD_COLUMNS,
                           filters=[("variable", "==", "temperature_c")])
    fresh = evaluation.evaluate_fold_variable(data, "split_fold_2", "temperature_c")
    stored = results["folds"]["split_fold_2"]["by_variable"]["temperature_c"]
    for method in evaluation.METHODS:
        for k in ("n", "mae", "rmse", "bias"):
            assert fresh["metrics"][method][k] == pytest.approx(stored["metrics"][method][k], rel=1e-12)
