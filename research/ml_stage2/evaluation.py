"""
ML Stage 2 runner: Model C (fixed-config HistGradientBoostingRegressor)
compared with Stage 1's A_bilinear, A_nearest and B_ridge on the EXACT
Phase 2D folds. Writes research/ml_stage2/stage2_results.json.

    python research/ml_stage2/evaluation.py

Stage 1 code is imported (never modified) so A/B are recomputed identically
on the same test rows; research/baselines/baseline_results.json is not
touched. No model file is written.
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

from baselines import baseline as stage1  # noqa: E402
from baselines.evaluation import (  # noqa: E402
    EVALUATION_STATEMENT, FOLD_COLUMNS, SPATIAL_STATEMENT, fold_leakage_audit,
)
from baselines.metrics import error_metrics  # noqa: E402
from ml_stage2.features import FEATURES, FORBIDDEN_FEATURES, VARIABLES, build_feature_frame, coarse_wide  # noqa: E402
from ml_stage2.model import CONFIG, fit_tree, model_summary, predict_tree  # noqa: E402
from multi_gp.build import DATASET_PATH, MANIFEST_PATH  # noqa: E402

RESULTS_PATH = Path(__file__).resolve().parent / "stage2_results.json"
METHODS = ["A_bilinear", "A_nearest", "B_ridge", "C_hgb"]
LOAD_COLUMNS = sorted(set(
    ["variable", "timestamp_utc", "gp_name", "cell_group_id", "in_primary_population", "target_value",
     "coarse_bilinear_value", "coarse_nearest_value"] + stage1.FEATURES + FOLD_COLUMNS
))
FRAMING = ("Reanalysis-to-reanalysis spatial transfer: ERA5 0.25 deg coarse inputs + static GP context "
           "-> ERA5-Land 0.1 deg nearest-cell reanalysis proxy.")


def invalid_count(variable: str, pred: np.ndarray) -> int:
    if variable in ("rainfall_mm", "wind_speed_kmph"):
        return int((pred < 0).sum())
    if variable == "relative_humidity_pct":
        return int(((pred < 0) | (pred > 100)).sum())
    return 0


def constrain(variable: str, pred: np.ndarray) -> np.ndarray:
    """POST-PROCESSING DIAGNOSTIC ONLY -- never replaces raw results."""
    if variable in ("rainfall_mm", "wind_speed_kmph"):
        return np.maximum(pred, 0.0)
    if variable == "relative_humidity_pct":
        return np.clip(pred, 0.0, 100.0)
    return pred


def fold_predictions(frame: pd.DataFrame, fold_col: str) -> tuple[pd.DataFrame, dict[str, np.ndarray], dict]:
    train = frame[frame[fold_col] == "train"]
    test = frame[frame[fold_col] == "test"]
    ridge = stage1.fit_ridge(train[stage1.FEATURES].to_numpy(), train["target_value"].to_numpy())
    tree = fit_tree(train[FEATURES].to_numpy(), train["target_value"].to_numpy())
    preds = {
        "A_bilinear": test["coarse_bilinear_value"].to_numpy(),
        "A_nearest": test["coarse_nearest_value"].to_numpy(),
        "B_ridge": stage1.predict_ridge(ridge, test[stage1.FEATURES].to_numpy()),
        "C_hgb": predict_tree(tree, test[FEATURES].to_numpy()),
    }
    return test, preds, {"C_hgb": model_summary(tree, len(train)), "n_train": int(len(train))}


def score(variable: str, test: pd.DataFrame, preds: dict) -> dict:
    y = test["target_value"].to_numpy()
    raw, constrained = {}, {}
    for m, p in preds.items():
        raw[m] = {**error_metrics(p, y), "invalid_predictions": invalid_count(variable, p)}
        constrained[m] = error_metrics(constrain(variable, p), y)
    diff = lambda a, b: {k: raw[a][k] - raw[b][k] for k in ("mae", "rmse", "bias")}  # noqa: E731
    return {
        "test_gps": sorted(test["gp_name"].unique().tolist()),
        "n_test_records": int(len(test)),
        "n_test_hours": int(test["timestamp_utc"].nunique()),
        "raw": raw,
        "constrained_diagnostic": constrained,
        "C_minus_A_bilinear": diff("C_hgb", "A_bilinear"),
        "C_minus_B_ridge": diff("C_hgb", "B_ridge"),
    }


def aggregate(per_fold: dict, variable: str, pooled_parts: dict) -> dict:
    out = {"raw": {}, "constrained_diagnostic": {}}
    for block in ("raw", "constrained_diagnostic"):
        for m in METHODS:
            vals = {k: [per_fold[f][variable][block][m][k] for f in FOLD_COLUMNS] for k in ("mae", "rmse", "bias")}
            out[block][m] = {
                **{f"{k}_mean_over_folds": float(np.mean(v)) for k, v in vals.items()},
                **{f"{k}_std_over_folds": float(np.std(v, ddof=1)) for k, v in vals.items()},
                "n_test_records_total": int(sum(per_fold[f][variable][block][m]["n"] for f in FOLD_COLUMNS)),
            }
            if block == "raw":
                out[block][m]["invalid_predictions_total"] = int(
                    sum(per_fold[f][variable]["raw"][m]["invalid_predictions"] for f in FOLD_COLUMNS))
            p, y = pooled_parts[m]
            pp = np.concatenate(p)
            out[block][m]["row_pooled"] = error_metrics(pp if block == "raw" else constrain(variable, pp), np.concatenate(y))
    r = out["raw"]
    for other in ("A_bilinear", "B_ridge"):
        out[f"C_minus_{other}_mean_over_folds"] = {
            k: r["C_hgb"][f"{k}_mean_over_folds"] - r[other][f"{k}_mean_over_folds"] for k in ("mae", "rmse", "bias")}
        out[f"folds_where_C_mae_below_{other}"] = [
            f for f in FOLD_COLUMNS
            if per_fold[f][variable]["raw"]["C_hgb"]["mae"] < per_fold[f][variable]["raw"][other]["mae"]]
    return out


def evaluate(data: pd.DataFrame, manifest: dict) -> dict:
    if set(FEATURES) & FORBIDDEN_FEATURES:
        raise RuntimeError("STOP: a forbidden column is listed as a feature")
    if "Mamballi" in set(data["gp_name"]):
        raise RuntimeError("STOP: Mamballi has rows; it must be UNAVAILABLE")

    wide = coarse_wide(data)
    folds_meta = {f["column"]: f for f in manifest["split_methodology"]["folds"]}
    per_fold = {f: {} for f in FOLD_COLUMNS}
    audits, fit_info = {}, {f: {} for f in FOLD_COLUMNS}
    aggregates = {}
    for variable in VARIABLES:
        frame = build_feature_frame(data, variable, wide)
        pooled = {m: ([], []) for m in METHODS}
        for fold_col in FOLD_COLUMNS:
            audits.setdefault(fold_col, fold_leakage_audit(frame, fold_col))
            test, preds, info = fold_predictions(frame, fold_col)
            per_fold[fold_col][variable] = score(variable, test, preds)
            fit_info[fold_col][variable] = info
            for m, p in preds.items():
                pooled[m][0].append(p)
                pooled[m][1].append(test["target_value"].to_numpy())
        aggregates[variable] = aggregate(per_fold, variable, pooled)

    rq = manifest["rainfall_quality"]
    return {
        "type": "YelandurMLStage2",
        "evaluation_statement": EVALUATION_STATEMENT,
        "spatial_sample_statement": SPATIAL_STATEMENT,
        "framing": FRAMING,
        "effective_spatial_sample_size": "4 ERA5-Land spatial cell groups",
        "row_independence_note": (f"The dataset's {len(data):,} rows are NOT independent samples."),
        "dataset": {"file": manifest["dataset_file"], "sha256": manifest.get("dataset_file_sha256"),
                    "row_count": int(len(data))},
        "methods": {
            "A_bilinear": "coarse_bilinear_value (Stage 1 Baseline A); no training",
            "A_nearest": "coarse_nearest_value (Stage 1, transparency); no training",
            "B_ridge": f"Stage 1 Baseline B, recomputed with the unchanged Stage 1 code (features: {stage1.FEATURES})",
            "C_hgb": "sklearn HistGradientBoostingRegressor, one fixed configuration, one model per fold x variable",
        },
        "C_config": CONFIG,
        "C_features": FEATURES,
        "C_feature_notes": {
            "era5_*": "ERA5 0.25 deg values bilinearly paired to the target cell, SAME timestamp as the row",
            "sin/cos_hour": "UTC hour of the row's own timestamp, period 24 h",
            "sin/cos_day_of_year": "day-of-year of the row's own timestamp, period = that year's length",
        },
        "excluded_from_features": sorted(FORBIDDEN_FEATURES),
        "physical_bounds": {"rainfall_mm": ">= 0", "relative_humidity_pct": "0-100", "wind_speed_kmph": ">= 0",
                            "temperature_c": "none checked", "dewpoint_c": "none checked"},
        "constrained_diagnostic_note": (
            "POST-PROCESSING DIAGNOSTIC ONLY: rainfall and wind clipped at 0, RH clipped to 0-100, applied AFTER "
            "prediction to every method. Raw results are the primary results and are not replaced."),
        "error_sign_convention": "bias = mean(prediction - target)",
        "folds": {
            f: {"held_out_cell_group": folds_meta[f]["held_out_cell_group"],
                "leakage_audit": audits[f],
                "by_variable": per_fold[f],
                "fit_info": fit_info[f]}
            for f in FOLD_COLUMNS
        },
        "aggregate_by_variable": aggregates,
        "population": {"agara": "PARTIAL -- excluded from every fold", "mamballi": "UNAVAILABLE -- zero rows"},
        "rainfall": {
            "processing": "Unchanged Phase 2D rainfall processing.",
            "missing_first_hour_rows": rq["target_missing_rows"],
            "tiny_negative_steps_clamped_target_rows": rq["target_rainfall_clamped_rows"],
            "max_abs_clamped_step_mm": rq["max_abs_clamped_step_mm"],
        },
        "stop_condition": "Stage 2 only: no neural network, no hyperparameter tuning.",
    }


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest() != manifest.get("dataset_file_sha256"):
        raise RuntimeError("STOP: dataset file does not match the Phase 2D manifest hash")
    data = pd.read_parquet(DATASET_PATH, columns=LOAD_COLUMNS)
    results = evaluate(data, manifest)
    RESULTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
