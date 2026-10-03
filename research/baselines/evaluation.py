"""
Runs ML Stage 1 (Baseline A + Baseline B) over the EXISTING Phase 2D folds
and writes research/baselines/baseline_results.json.

    python research/baselines/evaluation.py

Reads, never modifies: data/training/yelandur_multi_gp.parquet and
research/multi_gp/yelandur_multi_gp_manifest.json. Stores coefficients in the
results JSON only -- no model file is written.
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from baselines.baseline import FEATURES, FORBIDDEN_FEATURES, RIDGE_ALPHA, TARGET, fit_ridge, model_summary, predict_ridge  # noqa: E402
from baselines.metrics import error_metrics  # noqa: E402
from multi_gp.build import DATASET_PATH, MANIFEST_PATH  # noqa: E402

RESULTS_PATH = Path(__file__).resolve().parent / "baseline_results.json"

EVALUATION_STATEMENT = "Evaluation against ERA5-Land reanalysis proxy — not observation."
SPATIAL_STATEMENT = (
    "The effective spatial sample comprises 4 ERA5-Land cell groups, so these results are "
    "exploratory and do not establish generalized Panchayat-level forecasting skill."
)
FRAMING = "This experiment measures reanalysis-to-reanalysis spatial transfer (ERA5 0.25 deg -> ERA5-Land 0.1 deg)."

VARIABLES = ["temperature_c", "dewpoint_c", "relative_humidity_pct", "rainfall_mm", "wind_speed_kmph"]
FOLD_COLUMNS = ["split_fold_1", "split_fold_2", "split_fold_3", "split_fold_4"]
METHODS = ["A_bilinear", "A_nearest", "B_ridge"]
MIN_GAP = pd.Timedelta(days=7)

LOAD_COLUMNS = sorted(set(
    FEATURES + [TARGET, "coarse_nearest_value", "variable", "timestamp_utc", "gp_name", "coverage_status",
                "in_primary_population", "cell_group_id"] + FOLD_COLUMNS
))


def _out_of_range(variable: str, pred: np.ndarray) -> int:
    if variable in ("rainfall_mm", "wind_speed_kmph"):
        return int((pred < 0).sum())
    if variable == "relative_humidity_pct":
        return int(((pred < 0) | (pred > 100)).sum())
    return 0


def fold_leakage_audit(data: pd.DataFrame, fold_col: str) -> dict:
    train = data[data[fold_col] == "train"]
    test = data[data[fold_col] == "test"]
    train_groups = set(train["cell_group_id"])
    test_groups = set(test["cell_group_id"])
    gap = test["timestamp_utc"].min() - train["timestamp_utc"].max()
    audit = {
        "train_cell_groups": sorted(train_groups),
        "test_cell_groups": sorted(test_groups),
        "cell_groups_disjoint": train_groups.isdisjoint(test_groups),
        "train_last_timestamp_utc": str(train["timestamp_utc"].max()),
        "test_first_timestamp_utc": str(test["timestamp_utc"].min()),
        "temporal_gap_hours": float(gap / pd.Timedelta(hours=1)),
        "temporal_gap_at_least_7_days": bool(gap >= MIN_GAP),
        "partial_or_nonprimary_rows_used": int((~train["in_primary_population"]).sum()
                                               + (~test["in_primary_population"]).sum()),
        "agara_rows_used": int((train["gp_name"] == "Agara").sum() + (test["gp_name"] == "Agara").sum()),
        "missing_target_rows_used": int(train[TARGET].isna().sum() + test[TARGET].isna().sum()),
    }
    if not (audit["cell_groups_disjoint"] and audit["temporal_gap_at_least_7_days"]
            and audit["partial_or_nonprimary_rows_used"] == 0 and audit["missing_target_rows_used"] == 0):
        raise RuntimeError(f"STOP: leakage audit failed for {fold_col}: {audit}")
    return audit


def evaluate_fold_variable(data: pd.DataFrame, fold_col: str, variable: str) -> dict:
    rows = data[data["variable"] == variable]
    train = rows[rows[fold_col] == "train"]
    test = rows[rows[fold_col] == "test"]
    y_test = test[TARGET].to_numpy()

    model = fit_ridge(train[FEATURES].to_numpy(), train[TARGET].to_numpy())
    pred_b = predict_ridge(model, test[FEATURES].to_numpy())
    preds = {
        "A_bilinear": test["coarse_bilinear_value"].to_numpy(),
        "A_nearest": test["coarse_nearest_value"].to_numpy(),
        "B_ridge": pred_b,
    }
    metrics = {m: error_metrics(p, y_test) for m, p in preds.items()}
    for m, p in preds.items():
        metrics[m]["physically_out_of_range_predictions"] = _out_of_range(variable, p)
    return {
        "test_gps": sorted(test["gp_name"].unique().tolist()),
        "n_test_records": int(len(test)),
        "n_test_hours": int(test["timestamp_utc"].nunique()),
        "n_train_records": int(len(train)),
        "metrics": metrics,
        "B_minus_A_bilinear": {k: metrics["B_ridge"][k] - metrics["A_bilinear"][k] for k in ("mae", "rmse", "bias")},
        "B_ridge_model": model_summary(model),
    }


def aggregate(per_fold: dict, variable: str, data: pd.DataFrame | None = None) -> dict:
    """Unweighted mean/std across the 4 folds (each cell group counts once),
    plus row-pooled metrics recomputed from the folds' test rows."""
    out = {}
    for method in METHODS:
        vals = {k: [per_fold[f][variable]["metrics"][method][k] for f in per_fold] for k in ("mae", "rmse", "bias")}
        out[method] = {
            **{f"{k}_mean_over_folds": float(np.mean(v)) for k, v in vals.items()},
            **{f"{k}_std_over_folds": float(np.std(v, ddof=1)) for k, v in vals.items()},
            "n_test_records_total": int(sum(per_fold[f][variable]["metrics"][method]["n"] for f in per_fold)),
        }
    out["B_minus_A_bilinear_mean_over_folds"] = {
        k: out["B_ridge"][f"{k}_mean_over_folds"] - out["A_bilinear"][f"{k}_mean_over_folds"]
        for k in ("mae", "rmse", "bias")
    }
    if data is not None:
        rows = data[data["variable"] == variable]
        pooled = {m: ([], []) for m in METHODS}
        for fold_col in FOLD_COLUMNS:
            r = rows[rows[fold_col] == "test"]
            train = rows[rows[fold_col] == "train"]
            model = fit_ridge(train[FEATURES].to_numpy(), train[TARGET].to_numpy())
            for m, p in (("A_bilinear", r["coarse_bilinear_value"].to_numpy()),
                         ("A_nearest", r["coarse_nearest_value"].to_numpy()),
                         ("B_ridge", predict_ridge(model, r[FEATURES].to_numpy()))):
                pooled[m][0].append(p)
                pooled[m][1].append(r[TARGET].to_numpy())
        out["row_pooled"] = {m: error_metrics(np.concatenate(p), np.concatenate(t)) for m, (p, t) in pooled.items()}
    return out


def evaluate(data: pd.DataFrame, manifest: dict) -> dict:
    if set(FEATURES) & FORBIDDEN_FEATURES:
        raise RuntimeError("STOP: a forbidden column is listed as a feature")
    if "Mamballi" in set(data["gp_name"]):
        raise RuntimeError("STOP: Mamballi has rows; it must be UNAVAILABLE")

    folds_meta = {f["column"]: f for f in manifest["split_methodology"]["folds"]}
    per_fold, audits = {}, {}
    for fold_col in FOLD_COLUMNS:
        audits[fold_col] = fold_leakage_audit(data, fold_col)
        per_fold[fold_col] = {v: evaluate_fold_variable(data, fold_col, v) for v in VARIABLES}

    rain = data[data["variable"] == "rainfall_mm"]
    rq = manifest["rainfall_quality"]
    return {
        "type": "YelandurBaselinesStage1",
        "evaluation_statement": EVALUATION_STATEMENT,
        "spatial_sample_statement": SPATIAL_STATEMENT,
        "framing": FRAMING,
        "effective_spatial_sample_size": "4 ERA5-Land spatial cell groups",
        "row_independence_note": (
            f"The dataset's {len(data):,} rows are NOT independent samples: GPs in the same cell group share "
            "identical target series, hourly values are autocorrelated, and neighbouring cells are highly correlated."
        ),
        "dataset": {
            "file": manifest["dataset_file"],
            "sha256": manifest.get("dataset_file_sha256"),
            "row_count": int(len(data)),
            "manifest": "research/multi_gp/yelandur_multi_gp_manifest.json",
        },
        "methods": {
            "A_bilinear": "prediction = coarse_bilinear_value (ERA5 0.25 deg bilinear to target cell center); no training",
            "A_nearest": "prediction = coarse_nearest_value (nearest ERA5 0.25 deg point); no training; transparency only",
            "B_ridge": (f"ridge regression (alpha={RIDGE_ALPHA}, fixed a priori, no tuning) on standardized features "
                        "fit per fold and per variable on that fold's TRAINING rows only"),
        },
        "features_B": FEATURES,
        "excluded_from_features": sorted(FORBIDDEN_FEATURES),
        "variables": VARIABLES,
        "error_sign_convention": "bias = mean(prediction - target)",
        "folds": {
            col: {"held_out_cell_group": folds_meta[col]["held_out_cell_group"],
                  "leakage_audit": audits[col],
                  "by_variable": per_fold[col]}
            for col in FOLD_COLUMNS
        },
        "aggregate_by_variable": {v: aggregate(per_fold, v, data) for v in VARIABLES},
        "population": {
            "primary_gps": sorted(data.loc[data["in_primary_population"], "gp_name"].unique().tolist()),
            "agara": "PARTIAL -- excluded from every fold's train and test rows (see leakage_audit.agara_rows_used)",
            "mamballi": "UNAVAILABLE -- zero rows in the dataset",
        },
        "rainfall": {
            "processing": "Unchanged Phase 2D rainfall (ERA5-Land de-accumulated with pipeline.units; ERA5 tp already hourly).",
            "missing_first_hour_rows": int(rain[TARGET].isna().sum()),
            "missing_first_hour_rows_used_in_any_fold": int(sum(
                rain.loc[rain[TARGET].isna(), c].isin(["train", "test"]).sum() for c in FOLD_COLUMNS)),
            "tiny_negative_steps_clamped_target_rows": rq["target_rainfall_clamped_rows"],
            "tiny_negative_steps_clamped_area_weighted_rows": rq["area_weighted_rainfall_clamped_rows"],
            "max_abs_clamped_step_mm": rq["max_abs_clamped_step_mm"],
            "note": "Clamped steps are a ~0.000034 mm float32 rounding artifact, documented in the Phase 2D manifest.",
        },
        "stop_condition": "Stage 1 only: no neural network, no tree ensembles, no hyperparameter optimization.",
    }


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    actual_sha = hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest()
    if actual_sha != manifest.get("dataset_file_sha256"):
        raise RuntimeError("STOP: dataset file does not match the Phase 2D manifest hash")
    data = pd.read_parquet(DATASET_PATH, columns=LOAD_COLUMNS)
    results = evaluate(data, manifest)
    RESULTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False, sort_keys=False), encoding="utf-8")
    print(f"Wrote {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
