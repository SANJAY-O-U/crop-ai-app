"""
ML Stage 3A feature ablation (research/ml_stage3_ablation/).

Leakage protections from Stage 2 are re-verified for EVERY variant
(C1..C4) on a small synthetic Phase-2D-shaped frame. Contract tests read
the committed ablation_results.json.
"""

import json

import numpy as np
import pandas as pd
import pytest

from ml_stage2 import features as s2_features
from ml_stage2 import model as s2_model
from ml_stage3_ablation import evaluation
from ml_stage3_ablation.variants import INCREMENTS, VARIANT_NAMES, VARIANTS

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
            for v in s2_features.VARIABLES:
                coarse = 20 + rng.normal()
                rows.append({
                    "gp_name": name, "cell_group_id": group, "in_primary_population": primary,
                    "variable": v, "timestamp_utc": ts,
                    "coarse_bilinear_value": coarse, "coarse_nearest_value": coarse + 0.3,
                    "elevation_mean_m": elev, "elevation_range_m": elev / 10,
                    "centroid_to_cell_km": 3.0 if group == "cellA" else 5.0, "intersecting_cell_count": 2,
                    "target_value": coarse - 0.004 * (elev - 700) + 0.5 * np.sin(ts.hour) + rng.normal(scale=0.05),
                    "area_weighted_value": coarse + 1.0,
                    "target_cell_latitude": 12.1 if group == "cellA" else 12.0, "target_cell_longitude": 77.0,
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


def _preds(df, variant, variable="temperature_c"):
    frame = s2_features.build_feature_frame(df, variable)
    _, pred = evaluation.fit_predict(frame, "split_fold_1", VARIANTS[variant])
    return pred


# ---------------------------------------------------------------------
# Variant definitions
# ---------------------------------------------------------------------

def test_variants_are_nested_and_c4_equals_stage2_model_c():
    assert VARIANT_NAMES == ["C1_coarse_weather", "C2_plus_elevation", "C3_plus_spatial", "C4_plus_time_full_C"]
    for a, b in zip(VARIANT_NAMES, VARIANT_NAMES[1:]):
        assert VARIANTS[b][: len(VARIANTS[a])] == VARIANTS[a]
    assert VARIANTS["C1_coarse_weather"] == s2_features.COARSE_FEATURES
    assert VARIANTS["C2_plus_elevation"][5:] == ["elevation_mean_m", "elevation_range_m"]
    assert VARIANTS["C3_plus_spatial"][7:] == ["centroid_to_cell_km", "intersecting_cell_count"]
    assert VARIANTS["C4_plus_time_full_C"] == s2_features.FEATURES
    assert [g for _, _, g in INCREMENTS[:3]] == ["elevation", "spatial_context", "temporal"]


def test_same_fixed_config_as_stage2():
    assert evaluation.CONFIG is s2_model.CONFIG


@pytest.mark.parametrize("variant", VARIANT_NAMES)
def test_no_forbidden_feature_in_any_variant(variant):
    assert not set(VARIANTS[variant]) & s2_features.FORBIDDEN_FEATURES
    for col in ("target_value", "area_weighted_value", "cell_group_id", "target_cell_latitude",
                "target_cell_longitude", "gp_name", "panchayat_lgd_code", "split_fold_1", "temporal_period"):
        assert col not in VARIANTS[variant]


# ---------------------------------------------------------------------
# Leakage, re-verified per variant
# ---------------------------------------------------------------------

@pytest.mark.parametrize("variant", VARIANT_NAMES)
def test_target_and_area_weighted_values_do_not_affect_predictions(variant):
    df = _synthetic()
    changed = df.copy()
    test_rows = changed["split_fold_1"] == "test"
    changed.loc[test_rows, "target_value"] += 1000.0
    changed["area_weighted_value"] = -999.0
    assert np.array_equal(_preds(df, variant), _preds(changed, variant))


@pytest.mark.parametrize("variant", VARIANT_NAMES)
def test_cell_identity_gp_identity_and_other_folds_do_not_affect_predictions(variant):
    df = _synthetic()
    changed = df.copy()
    changed["cell_group_id"] = changed["cell_group_id"].map({"cellA": "P", "cellB": "Q"})
    changed["target_cell_latitude"] = 0.0
    changed["target_cell_longitude"] = 0.0
    changed["gp_name"] = changed["gp_name"].map({"G1": "X1", "G2": "X2", "G3": "X3", "Agara": "Agara"})
    changed["split_fold_3"] = "excluded"
    assert np.array_equal(_preds(df, variant), _preds(changed, variant))


@pytest.mark.parametrize("variant", VARIANT_NAMES)
def test_no_future_values_in_variant_features(variant):
    df = _synthetic()
    frame = s2_features.build_feature_frame(df, "dewpoint_c")
    probe = frame.iloc[150]
    later = df.copy()
    later.loc[later["timestamp_utc"] > probe["timestamp_utc"], "coarse_bilinear_value"] = 1e6
    f2 = s2_features.build_feature_frame(later, "dewpoint_c")
    same = f2[(f2["gp_name"] == probe["gp_name"]) & (f2["timestamp_utc"] == probe["timestamp_utc"])].iloc[0]
    for f in VARIANTS[variant]:
        assert same[f] == probe[f], f


@pytest.mark.parametrize("variant", VARIANT_NAMES)
def test_fit_only_on_training_rows(variant, monkeypatch):
    df = _synthetic()
    frame = s2_features.build_feature_frame(df, "wind_speed_kmph")
    seen = {}
    real = evaluation.fit_tree

    def spy(X, y):
        seen["X"], seen["y"] = X, y
        return real(X, y)

    monkeypatch.setattr(evaluation, "fit_tree", spy)
    evaluation.fit_predict(frame, "split_fold_1", VARIANTS[variant])
    train = frame[frame["split_fold_1"] == "train"]
    assert np.array_equal(seen["X"], train[VARIANTS[variant]].to_numpy(dtype=float))
    assert np.array_equal(seen["y"], train["target_value"].to_numpy(dtype=float))


@pytest.mark.parametrize("variant", VARIANT_NAMES)
def test_deterministic(variant):
    assert np.array_equal(_preds(_synthetic(), variant), _preds(_synthetic(), variant))


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
        pytest.skip("ablation_results.json not generated")
    return json.loads(evaluation.RESULTS_PATH.read_text(encoding="utf-8"))


def test_c4_reproduces_stage2_exactly(results):
    check = results["c4_reproduction"]
    assert check["exact_match"] and check["max_abs_difference"] == 0 and check["cells_compared"] == 100
    stage2 = json.loads(evaluation.STAGE2_RESULTS_PATH.read_text(encoding="utf-8"))
    for f, fold in results["folds"].items():
        for v in s2_features.VARIABLES:
            mine = fold["by_variable"][v]["C4_plus_time_full_C"]
            ref = stage2["folds"][f]["by_variable"][v]["raw"]["C_hgb"]
            for k in ("n", "mae", "rmse", "bias", "invalid_predictions"):
                assert mine[k] == ref[k]


def test_spatial_separation_and_temporal_gap(results):
    held = set()
    for fold in results["folds"].values():
        a = fold["leakage_audit"]
        assert a["cell_groups_disjoint"] and a["test_cell_groups"] == [fold["held_out_cell_group"]]
        assert a["temporal_gap_at_least_7_days"] and a["temporal_gap_hours"] >= 168
        assert a["agara_rows_used"] == 0
        held.add(fold["held_out_cell_group"])
    assert len(held) == 4


def test_every_variant_scored_on_identical_rows(results):
    for fold in results["folds"].values():
        for v in s2_features.VARIABLES:
            cell = fold["by_variable"][v]
            ns = {cell[m]["n"] for m in ["A_bilinear"] + VARIANT_NAMES}
            assert ns == {cell["n_test_records"]}
            assert "Agara" not in cell["test_gps"] and "Mamballi" not in cell["test_gps"]


def test_increments_are_consistent_differences(results):
    for v in s2_features.VARIABLES:
        agg = results["aggregate_by_variable"][v]
        for a, b, _ in INCREMENTS:
            d = agg["increments"][f"{a}->{b}"]["fold_mean_delta"]["mae"]
            assert d == pytest.approx(agg[b]["mae_mean_over_folds"] - agg[a]["mae_mean_over_folds"])


def test_statements_and_forbidden_phrases(results):
    assert results["evaluation_statement"] == "Evaluation against ERA5-Land reanalysis proxy — not observation."
    assert "do not establish generalized Panchayat-level forecasting skill" in results["spatial_sample_statement"]
    readme = (evaluation.RESULTS_PATH.parent / "README.md").read_text(encoding="utf-8").lower()
    text = json.dumps(results, ensure_ascii=False).lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in text and phrase not in readme, phrase


def test_real_variant_recompute_matches_committed_results(results):
    from multi_gp.build import DATASET_PATH

    if not DATASET_PATH.exists():
        pytest.skip("Phase 2D Parquet dataset not present locally")
    data = pd.read_parquet(DATASET_PATH, columns=evaluation.LOAD_COLUMNS)
    frame = s2_features.build_feature_frame(data, "temperature_c")
    test, pred = evaluation.fit_predict(frame, "split_fold_2", VARIANTS["C2_plus_elevation"])
    fresh = evaluation.error_metrics(pred, test["target_value"].to_numpy())
    stored = results["folds"]["split_fold_2"]["by_variable"]["temperature_c"]["C2_plus_elevation"]
    for k in ("n", "mae", "rmse", "bias"):
        assert fresh[k] == pytest.approx(stored[k], rel=1e-12)
