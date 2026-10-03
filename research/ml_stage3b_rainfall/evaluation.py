"""
ML Stage 3B: precipitation-specialized two-stage model vs A_bilinear and the
existing generic C4 HGB rainfall regression, on the exact Phase 2D folds.

    python research/ml_stage3b_rainfall/evaluation.py

Writes research/ml_stage3b_rainfall/rainfall_results.json only. Earlier
stages are imported/read, never written. No model file is saved.
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

from baselines.evaluation import EVALUATION_STATEMENT, FOLD_COLUMNS, SPATIAL_STATEMENT, fold_leakage_audit  # noqa: E402
from ml_stage2.evaluation import LOAD_COLUMNS  # noqa: E402
from ml_stage2.evaluation import RESULTS_PATH as STAGE2_RESULTS_PATH  # noqa: E402
from ml_stage2.features import FEATURES, FORBIDDEN_FEATURES, build_feature_frame, coarse_wide  # noqa: E402
from ml_stage2.model import CONFIG as C4_CONFIG  # noqa: E402
from ml_stage2.model import fit_tree, predict_tree  # noqa: E402
from ml_stage3b_rainfall import config  # noqa: E402
from ml_stage3b_rainfall.metrics import occurrence_metrics, rainfall_metrics  # noqa: E402
from ml_stage3b_rainfall.model import fit_two_stage, predict_two_stage  # noqa: E402
from multi_gp.build import DATASET_PATH, MANIFEST_PATH  # noqa: E402
from multi_gp.splits import EMBARGO_START  # noqa: E402

RESULTS_PATH = Path(__file__).resolve().parent / "rainfall_results.json"
VARIABLE = "rainfall_mm"
METHODS = ["A_bilinear", "C4_hgb_regression", "S_two_stage"]

UPSTREAM_ARTIFACTS = {
    "stage1_results": _RESEARCH_DIR / "baselines" / "baseline_results.json",
    "stage2_results": STAGE2_RESULTS_PATH,
    "stage3a_results": _RESEARCH_DIR / "ml_stage3_ablation" / "ablation_results.json",
    "phase2d_manifest": MANIFEST_PATH,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fold_predictions(frame: pd.DataFrame, fold_col: str) -> dict:
    train = frame[frame[fold_col] == "train"]
    test = frame[frame[fold_col] == "test"]
    c4 = fit_tree(train[FEATURES].to_numpy(), train["target_value"].to_numpy())
    fitted = fit_two_stage(train)
    s_raw, prob, is_wet = predict_two_stage(fitted, test[FEATURES].to_numpy())
    return {
        "train": train, "test": test, "fitted": fitted, "prob": prob, "classifier_wet": is_wet,
        "raw": {
            "A_bilinear": test["coarse_bilinear_value"].to_numpy(),
            "C4_hgb_regression": predict_tree(c4, test[FEATURES].to_numpy()),
            "S_two_stage": s_raw,
        },
    }


def inner_split_audit(train: pd.DataFrame, test: pd.DataFrame, selection: dict) -> dict:
    val_end = pd.Timestamp(selection["inner_val_range_utc"][1])
    audit = {
        "inner_rows_are_training_rows_only": selection["inner_train_rows"] + selection["inner_val_rows"] <= len(train),
        "inner_val_ends_before_embargo": bool(val_end < EMBARGO_START),
        "inner_val_ends_before_test": bool(val_end < test["timestamp_utc"].min()),
        "inner_gap_hours": float((config.INNER_VAL_START - config.INNER_TRAIN_END_EXCLUSIVE) / pd.Timedelta(hours=1)),
    }
    if not all(v for k, v in audit.items() if k != "inner_gap_hours"):
        raise RuntimeError(f"STOP: threshold-selection split touches non-training data: {audit}")
    return audit


def _mean(values):
    vals = [v for v in values if v is not None]
    return float(np.mean(vals)) if vals else None


def evaluate(data: pd.DataFrame, manifest: dict) -> dict:
    if set(FEATURES) & FORBIDDEN_FEATURES:
        raise RuntimeError("STOP: forbidden feature")
    if "Mamballi" in set(data["gp_name"]):
        raise RuntimeError("STOP: Mamballi has rows; it must be UNAVAILABLE")

    frame = build_feature_frame(data, VARIABLE, coarse_wide(data))
    folds_meta = {f["column"]: f for f in manifest["split_methodology"]["folds"]}
    folds, pooled = {}, {m: ([], []) for m in METHODS}
    pooled_classifier = ([], [])
    for fold_col in FOLD_COLUMNS:
        audit = fold_leakage_audit(frame, fold_col)
        out = fold_predictions(frame, fold_col)
        test, y = out["test"], out["test"]["target_value"].to_numpy()
        selection = out["fitted"]["selection"]
        block = {
            "held_out_cell_group": folds_meta[fold_col]["held_out_cell_group"],
            "leakage_audit": audit,
            "threshold_selection": {**selection, "audit": inner_split_audit(out["train"], test, selection)},
            "n_test_records": int(len(test)),
            "n_train_records": int(len(out["train"])),
            "n_train_wet_records": out["fitted"]["n_train_wet"],
            "test_gps": sorted(test["gp_name"].unique().tolist()),
            "raw": {}, "constrained_diagnostic": {},
            "classifier_occurrence": occurrence_metrics(out["classifier_wet"], y > config.WET_THRESHOLD_MM),
        }
        for m in METHODS:
            p = out["raw"][m]
            block["raw"][m] = rainfall_metrics(p, y)
            block["constrained_diagnostic"][m] = rainfall_metrics(np.maximum(p, 0.0), y)
            pooled[m][0].append(p)
            pooled[m][1].append(y)
        pooled_classifier[0].append(out["classifier_wet"])
        pooled_classifier[1].append(y > config.WET_THRESHOLD_MM)
        folds[fold_col] = block

    fold_mean = {}
    for block_name in ("raw", "constrained_diagnostic"):
        fold_mean[block_name] = {}
        for m in METHODS:
            get = lambda f, *keys: _dig(folds[f][block_name][m], keys)  # noqa: E731
            fold_mean[block_name][m] = {
                "overall_mae": _mean([get(f, "overall", "mae") for f in FOLD_COLUMNS]),
                "overall_rmse": _mean([get(f, "overall", "rmse") for f in FOLD_COLUMNS]),
                "overall_bias": _mean([get(f, "overall", "bias") for f in FOLD_COLUMNS]),
                "occurrence_precision": _mean([get(f, "occurrence", "precision") for f in FOLD_COLUMNS]),
                "occurrence_recall": _mean([get(f, "occurrence", "recall") for f in FOLD_COLUMNS]),
                "occurrence_f1": _mean([get(f, "occurrence", "f1") for f in FOLD_COLUMNS]),
                "wet_hour_amount_mae": _mean([get(f, "amount_on_observed_wet_hours", "mae") for f in FOLD_COLUMNS]),
                "wet_hour_amount_bias": _mean([get(f, "amount_on_observed_wet_hours", "bias") for f in FOLD_COLUMNS]),
                "invalid_predictions_total": int(sum(get(f, "overall", "invalid_predictions") for f in FOLD_COLUMNS)),
            }

    pooled_out = {"raw": {}, "constrained_diagnostic": {}}
    for m in METHODS:
        p, y = np.concatenate(pooled[m][0]), np.concatenate(pooled[m][1])
        pooled_out["raw"][m] = rainfall_metrics(p, y)
        pooled_out["constrained_diagnostic"][m] = rainfall_metrics(np.maximum(p, 0.0), y)
    pooled_out["classifier_occurrence"] = occurrence_metrics(
        np.concatenate(pooled_classifier[0]), np.concatenate(pooled_classifier[1]))

    rq = manifest["rainfall_quality"]
    return {
        "type": "YelandurMLStage3BRainfall",
        "evaluation_statement": EVALUATION_STATEMENT,
        "spatial_sample_statement": SPATIAL_STATEMENT,
        "effective_spatial_sample_size": "4 ERA5-Land spatial cell groups",
        "row_independence_note": f"The rainfall rows ({len(frame):,}) are NOT independent samples.",
        "dataset": {"file": manifest["dataset_file"], "sha256": manifest.get("dataset_file_sha256")},
        "methods": {
            "A_bilinear": "coarse_bilinear_value (ERA5 0.25 deg bilinear); no training",
            "C4_hgb_regression": "Stage 2 Model C rainfall regression (ml_stage2.model.CONFIG, 13 features), refit here",
            "S_two_stage": ("HistGradientBoostingClassifier (wet = target > 0.1 mm) gated by a per-fold threshold "
                            "selected on training rows only, then HistGradientBoostingRegressor(poisson) amount "
                            "trained on wet training hours; prediction = amount if p(wet) >= threshold else 0"),
        },
        "features": FEATURES,
        "wet_threshold_mm": config.WET_THRESHOLD_MM,
        "threshold_selection_method": {
            "grid": config.THRESHOLD_GRID,
            "inner_train": "fold training rows with timestamp < 2022-01-01T00Z",
            "inner_gap": "2022-01-01T00Z .. 2022-01-07T23Z (unused)",
            "inner_val": "fold training rows with timestamp >= 2022-01-08T00Z (ends 2022-12-24T23Z)",
            "criterion": "max inner-val F1; ties -> lowest threshold; classifier then refit on all training rows",
            "test_data_used": False,
        },
        "classifier_config": config.CLASSIFIER_CONFIG,
        "amount_config": config.AMOUNT_CONFIG,
        "c4_config": C4_CONFIG,
        "constrained_diagnostic_note": ("POST-PROCESSING DIAGNOSTIC ONLY: max(prediction, 0) applied after "
                                        "prediction. Raw results are primary and are not replaced."),
        "error_sign_convention": "bias = mean(prediction - target)",
        "metric_definitions": {
            "occurrence": "wet = value > 0.1 mm; precision/recall/F1 of predicted-wet vs observed-wet hours",
            "classifier_occurrence": "S_two_stage classifier decision (p >= threshold) vs observed-wet hours",
            "amount_on_observed_wet_hours": "MAE/RMSE/bias over hours with target > 0.1 mm",
            "amount_on_hit_hours": "MAE/RMSE/bias over hours both observed and predicted wet",
            "dry_hour_behaviour": "hours with target <= 0.1 mm",
        },
        "folds": folds,
        "fold_mean": fold_mean,
        "pooled": pooled_out,
        "c4_reproduction": c4_reproduction(folds),
        "rainfall_processing": {
            "note": "Unchanged Phase 2D rainfall processing.",
            "missing_first_hour_rows": rq["target_missing_rows"],
            "tiny_negative_steps_clamped_target_rows": rq["target_rainfall_clamped_rows"],
            "max_abs_clamped_step_mm": rq["max_abs_clamped_step_mm"],
        },
        "upstream_artifact_sha256": {k: sha256(p) for k, p in UPSTREAM_ARTIFACTS.items()},
        "stop_condition": "Stage 3B only.",
    }


def _dig(d, keys):
    for k in keys:
        d = d[k]
    return d


def c4_reproduction(folds: dict) -> dict:
    stage2 = json.loads(STAGE2_RESULTS_PATH.read_text(encoding="utf-8"))
    mismatches, max_abs = [], 0.0
    for f in FOLD_COLUMNS:
        mine = folds[f]["raw"]["C4_hgb_regression"]["overall"]
        ref = stage2["folds"][f]["by_variable"][VARIABLE]["raw"]["C_hgb"]
        for k in ("n", "mae", "rmse", "bias", "invalid_predictions"):
            d = abs(mine[k] - ref[k])
            max_abs = max(max_abs, d)
            if d:
                mismatches.append(f"{f}/{k}")
    if mismatches:
        raise RuntimeError(f"STOP: C4 rainfall does not reproduce Stage 2: {mismatches}")
    return {"compared_against": "Stage 2 C_hgb rainfall (raw)", "cells_compared": 20,
            "max_abs_difference": max_abs, "exact_match": True}


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if sha256(DATASET_PATH) != manifest.get("dataset_file_sha256"):
        raise RuntimeError("STOP: dataset file does not match the Phase 2D manifest hash")
    data = pd.read_parquet(DATASET_PATH, columns=LOAD_COLUMNS)
    results = evaluate(data, manifest)
    RESULTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
