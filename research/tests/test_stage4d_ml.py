"""
Stage 4D cross-area evaluation (research/stage4d_ml/).

Unit tests use small synthetic wide frames (always run). Contract tests
read the committed stage4d_results.json / per-fold results; tests needing
the gitignored Stage 4 Parquet files skip where they are absent.
"""

import json

import numpy as np
import pandas as pd
import pytest

from baselines import baseline as stage1
from ml_stage2 import model as s2_model
from ml_stage2.features import VARIABLES
from ml_stage3_ablation.variants import VARIANTS
from stage4d_ml import data4d, evaluate4d, leakage_checks, metrics4d, splits4d, train4d

FORBIDDEN_PHRASES = ["ground truth", "observed panchayat weather", "validated panchayat forecast",
                     "accurate panchayat weather", "actual panchayat weather prediction", "deployment-ready"]


# ---------------------------------------------------------------------
# Synthetic wide frame
# ---------------------------------------------------------------------

def _wide(seed=0):
    rng = np.random.default_rng(seed)
    ts = list(pd.date_range("2022-12-01", periods=24 * 20, freq="h", tz="UTC")) + \
        list(pd.date_range("2023-01-01", periods=24 * 5, freq="h", tz="UTC"))
    gps = [("g1", "A", "E5L_12.00N_77.10E", 650.0), ("g2", "A", "E5L_12.00N_77.10E", 700.0),
           ("g3", "B", "E5L_15.00N_75.00E", 900.0), ("g4", "C", "E5L_17.00N_76.00E", 500.0)]
    rows = []
    for gp, tp, cell, elev in gps:
        for t in ts:
            period = "test_period" if t >= pd.Timestamp("2023-01-01", tz="UTC") else (
                "embargo" if t >= pd.Timestamp("2022-12-25", tz="UTC") else "train_period")
            r = {"panchayat_lgd_code": gp, "taluka_panchayat_lgd_code": tp, "cell_group_id": cell,
                 "timestamp_utc": t, "temporal_period": period, "elevation_mean_m": elev,
                 "elevation_range_m": elev / 10, "centroid_to_cell_km": 3.0, "intersecting_cell_count": 2,
                 "coarse_nearest_distance_km": 8.0, "sin_hour": np.sin(t.hour), "cos_hour": np.cos(t.hour),
                 "sin_day_of_year": 0.1, "cos_day_of_year": 0.9}
            for v in VARIABLES:
                c = 20 + rng.normal()
                r[f"era5_{v}"] = c
                r[f"nearest_{v}"] = c + 0.2
                r[f"target_{v}"] = max(0.0, c - 0.004 * (elev - 700) + rng.normal(scale=0.1)) if v == "rainfall_mm" \
                    else c - 0.004 * (elev - 700) + rng.normal(scale=0.1)
            rows.append(r)
    return pd.DataFrame(rows)


AREA_FOLD = {"fold_id": "taluka_B", "test_tp": ["B"], "train_tp": ["A", "C"]}


# ---------------------------------------------------------------------
# Splits + leakage (synthetic)
# ---------------------------------------------------------------------

def test_masks_respect_geography_and_time():
    w = _wide()
    tr, te = splits4d.masks(w, "area", AREA_FOLD, "temperature_c")
    assert set(w.loc[tr, "taluka_panchayat_lgd_code"]) == {"A", "C"}
    assert set(w.loc[te, "taluka_panchayat_lgd_code"]) == {"B"}
    assert (w.loc[tr, "temporal_period"] == "train_period").all()
    assert (w.loc[te, "temporal_period"] == "test_period").all()


def test_cellblock_buffer_dropped_from_training():
    w = _wide()
    fold = {"fold_id": "cb", "test_cells": ["E5L_15.00N_75.00E"], "buffer_cells": ["E5L_12.00N_77.10E"]}
    tr, te = splits4d.masks(w, "cellblock", fold, "dewpoint_c")
    assert set(w.loc[tr, "cell_group_id"]) == {"E5L_17.00N_76.00E"}
    assert set(w.loc[te, "cell_group_id"]) == {"E5L_15.00N_75.00E"}


def test_isolation_audit_passes_and_detects_leakage():
    w = _wide()
    audit = leakage_checks.verify_fold_isolation(w, "area", AREA_FOLD, "temperature_c")
    assert audit["shared_gps"] == 0 and audit["shared_cells"] == 0 and audit["temporal_gap_hours"] >= 168
    leaky = w.copy()
    leaky.loc[leaky["panchayat_lgd_code"] == "g3", "cell_group_id"] = "E5L_12.00N_77.10E"  # test cell == training cell
    with pytest.raises(RuntimeError, match="cell leakage"):
        leakage_checks.verify_fold_isolation(leaky, "area", AREA_FOLD, "temperature_c")
    leaky2 = w.copy()
    leaky2.loc[leaky2["panchayat_lgd_code"] == "g1", "taluka_panchayat_lgd_code"] = "B"
    leaky2.loc[(leaky2["panchayat_lgd_code"] == "g1") & (leaky2["temporal_period"] == "train_period"),
               "taluka_panchayat_lgd_code"] = "A"
    with pytest.raises(RuntimeError, match="Panchayat leakage"):
        leakage_checks.verify_fold_isolation(leaky2, "area", AREA_FOLD, "temperature_c")


def test_feature_audit_rejects_forbidden_columns():
    for v in VARIABLES:
        leakage_checks.feature_audit(train4d.feature_lists(v))
    for bad in ("target_temperature_c", "panchayat_lgd_code", "cell_group_id", "taluka_holdout_fold",
                "area_weighted_value", "nearest_rainfall_mm", "timestamp_utc"):
        with pytest.raises(RuntimeError):
            leakage_checks.feature_audit({"X": ["era5_temperature_c", bad]})


def test_feature_lists_are_the_frozen_ones():
    assert train4d.C_VARIANTS["C1"] == VARIANTS["C1_coarse_weather"]
    assert train4d.C_VARIANTS["C4"] == VARIANTS["C4_plus_time_full_C"]
    for v in VARIABLES:
        b = train4d.b_features(v)
        assert b[0] == f"era5_{v}" and b[1:] == stage1.FEATURES[1:]


def test_nan_features_are_refused():
    with pytest.raises(RuntimeError):
        leakage_checks.verify_feature_matrix(np.array([[1.0, np.nan]]), ["a", "b"])


def test_preprocessing_fit_on_training_rows_only():
    w = _wide()
    tr, te = splits4d.masks(w, "area", AREA_FOLD, "temperature_c")
    _, _, info_a = train4d.fit_and_predict(w, tr, te, "temperature_c", methods=["B_ridge"])
    changed = w.copy()
    changed.loc[te, ["era5_temperature_c", "elevation_mean_m"]] *= 50  # held-out features altered
    changed.loc[te, "target_temperature_c"] += 1000                    # held-out targets altered
    _, _, info_b = train4d.fit_and_predict(changed, tr, te, "temperature_c", methods=["B_ridge"])
    assert info_a == info_b
    model = stage1.fit_ridge(w.loc[tr, train4d.b_features("temperature_c")].to_numpy(),
                             w.loc[tr, "target_temperature_c"].to_numpy())
    assert info_a["B_ridge"]["intercept"] == pytest.approx(model["intercept"])


def test_tree_predictions_unaffected_by_heldout_targets():
    w = _wide()
    tr, te = splits4d.masks(w, "area", AREA_FOLD, "wind_speed_kmph")
    p1, _, _ = train4d.fit_and_predict(w, tr, te, "wind_speed_kmph", methods=["C1", "C4"])
    changed = w.copy()
    changed.loc[te, "target_wind_speed_kmph"] = -999.0
    p2, _, _ = train4d.fit_and_predict(changed, tr, te, "wind_speed_kmph", methods=["C1", "C4"])
    for m in ("C1", "C4"):
        assert np.array_equal(p1[m], p2[m])


def test_frozen_configuration_and_determinism():
    assert s2_model.CONFIG["random_state"] == 0 and s2_model.CONFIG["early_stopping"] is False
    assert s2_model.CONFIG["max_iter"] == 200 and s2_model.CONFIG["min_samples_leaf"] == 200
    assert train4d.model_configuration()["C1..C4"]["hgb_config"] is s2_model.CONFIG
    w = _wide()
    tr, te = splits4d.masks(w, "area", AREA_FOLD, "temperature_c")
    a, _, _ = train4d.fit_and_predict(w, tr, te, "temperature_c")
    b, _, _ = train4d.fit_and_predict(w, tr, te, "temperature_c")
    assert all(metrics4d.prediction_hash(a[m]) == metrics4d.prediction_hash(b[m]) for m in train4d.METHODS)


def test_pooled_accumulator_is_exact():
    rng = np.random.default_rng(3)
    pool = metrics4d.Pooled()
    ps, ys = [], []
    for _ in range(3):
        p, y = rng.normal(size=50), rng.normal(size=50)
        pool.add(p, y, "temperature_c")
        ps.append(p)
        ys.append(y)
    ref = metrics4d.error_metrics(np.concatenate(ps), np.concatenate(ys))
    got = pool.result("temperature_c")
    assert got["n"] == ref["n"] and got["mae"] == pytest.approx(ref["mae"]) and got["rmse"] == pytest.approx(ref["rmse"])


# ---------------------------------------------------------------------
# Frozen split definitions (manifest; no data needed)
# ---------------------------------------------------------------------

def test_frozen_fold_definitions():
    f = splits4d.fold_definitions()
    assert len(f["area"]) == 11 and len(f["region"]) == 6 and len(f["cellblock"]) == 5
    assert f["district"]["equivalent_to"] == "taluka_holdout"
    all_tp = {t for x in f["area"] for t in x["test_tp"]}
    assert len(all_tp) == 11 and all(len(x["test_tp"]) == 1 for x in f["area"])
    assert sorted(t for x in f["region"] for t in x["test_tp"]) == sorted(all_tp)
    for x in f["area"] + f["region"]:
        assert not set(x["test_tp"]) & set(x["train_tp"])
        assert "6132" not in x["test_tp"] + x["train_tp"]  # Yelandur never a Stage 4 training/test area
    for x in f["cellblock"]:
        assert not set(x["test_cells"]) & set(x["buffer_cells"])
    assert f["temporal_split"]["test_period_utc"][0].startswith("2023-01-01")


# ---------------------------------------------------------------------
# Dataset identity (needs Parquet)
# ---------------------------------------------------------------------

def test_dataset_identity_matches_frozen_manifest():
    m = data4d.load_json(data4d.DATASET_MANIFEST)
    if not all((data4d.REPO / a["file"]).exists() for a in m["dataset_files"]):
        pytest.skip("Stage 4 Parquet files not present locally")
    ident = data4d.verify_dataset_identity()
    assert ident["row_total"] == 36_397_800 == m["row_total"]
    assert len(ident["files"]) == 11


# ---------------------------------------------------------------------
# Contract tests on committed results
# ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def results():
    if not evaluate4d.RESULTS_JSON.exists():
        pytest.skip("stage4d_results.json not generated")
    return json.loads(evaluate4d.RESULTS_JSON.read_text(encoding="utf-8"))


def test_results_identity_and_statements(results):
    assert results["dataset_identity"]["dataset_manifest_sha256"] == data4d.sha256(data4d.DATASET_MANIFEST)
    assert results["dataset_identity"]["design_manifest_sha256"] == data4d.sha256(data4d.DESIGN_MANIFEST)
    assert results["dataset_identity"]["row_total"] == 36_397_800
    assert "not observation" in results["evaluation_statement"]
    text = json.dumps(results, ensure_ascii=False).lower()
    readme = (evaluate4d.MODULE / "README.md").read_text(encoding="utf-8").lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in text and phrase not in readme, phrase


def test_results_fold_counts_and_variable_coverage(results):
    assert results["area_holdout"]["n_folds"] == 11
    assert results["region_holdout"]["n_folds"] == 6
    assert results["cellblock_diagnostic"]["n_folds"] == 5
    assert results["district_holdout"]["equivalent_to"] == "area_holdout" and results["district_holdout"]["verified"]
    for scheme in ("area_holdout", "region_holdout", "cellblock_diagnostic"):
        bv = results[scheme]["by_variable"]
        assert set(bv) == set(VARIABLES)
        for v in VARIABLES:
            assert set(train4d.METHODS) <= set(bv[v])
        assert "pooled_rainfall" in bv["rainfall_mm"]["C4"]


def test_results_no_leakage_in_any_fold(results):
    for scheme in ("area_holdout", "region_holdout", "cellblock_diagnostic"):
        for f in results[scheme]["folds"]:
            iso = f["isolation"]
            assert iso["shared_gps"] == 0 and iso["shared_cells"] == 0 and iso["temporal_gap_hours"] >= 168
            if scheme != "cellblock_diagnostic":
                assert iso["min_test_train_cell_separation"] >= 3
            else:
                assert iso["min_test_train_cell_separation"] >= 2


def test_karwar_exception_documented(results):
    assert "BELOW the original >= 6-cell criterion" in results["karwar_exception"]["note"]
    kf = [f for f in results["area_holdout"]["folds"] if f["fold_id"] == "taluka_6253"]
    assert len(kf) == 1 and kf[0]["geography"]["includes_karwar_exception"]
    assert kf[0]["geography"]["n_panchayats"] == 14 and kf[0]["geography"]["n_target_cells"] == 5
    others = [f for f in results["area_holdout"]["folds"] if f["fold_id"] != "taluka_6253"]
    assert not any(f["geography"]["includes_karwar_exception"] for f in others)


def test_reproducible_metrics(results):
    det = results["determinism_check"]
    assert det and det["identical"] and det["metrics_identical"] and det["compared"] == 35
    for p in sorted((evaluate4d.RESULTS / "area").glob("taluka_*.json"))[:2]:
        fold = json.loads(p.read_text(encoding="utf-8"))
        stored = next(f for f in results["area_holdout"]["folds"] if f["fold_id"] == fold["fold_id"])
        for v in VARIABLES:
            for m in train4d.METHODS:
                assert stored["metrics"][v][m]["mae"] == fold["variables"][v]["metrics"][m]["mae"]


def test_pooled_equals_sum_of_fold_parts(results):
    folds = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((evaluate4d.RESULTS / "area").glob("taluka_*.json"))]
    for v in VARIABLES:
        n = sum(f["variables"][v]["pooled_parts"]["C4"]["n"] for f in folds)
        mae = sum(f["variables"][v]["pooled_parts"]["C4"]["sum_abs"] for f in folds) / n
        assert results["area_holdout"]["by_variable"][v]["C4"]["pooled"]["mae"] == pytest.approx(mae)
