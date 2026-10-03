"""
ML Stage 3A: feature-group ablation of Model C.

Same fixed HistGradientBoostingRegressor configuration as Stage 2
(ml_stage2.model.CONFIG, imported -- not copied), same Phase 2D folds, same
feature construction (ml_stage2.features). Only the feature list changes:
C1 (coarse weather) -> C2 (+elevation) -> C3 (+spatial context) -> C4 (+time
= Stage 2 Model C). A_bilinear is scored on the same rows as a reference.

    python research/ml_stage3_ablation/evaluation.py

Writes research/ml_stage3_ablation/ablation_results.json. Stage 1/2 code and
results are imported/read only. No model file is written.
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
from baselines.metrics import error_metrics  # noqa: E402
from ml_stage2.evaluation import LOAD_COLUMNS, invalid_count  # noqa: E402
from ml_stage2.evaluation import RESULTS_PATH as STAGE2_RESULTS_PATH  # noqa: E402
from ml_stage2.features import FORBIDDEN_FEATURES, VARIABLES, build_feature_frame, coarse_wide  # noqa: E402
from ml_stage2.model import CONFIG, fit_tree, predict_tree  # noqa: E402
from ml_stage3_ablation.variants import INCREMENTS, VARIANT_NAMES, VARIANTS  # noqa: E402
from multi_gp.build import DATASET_PATH, MANIFEST_PATH  # noqa: E402

RESULTS_PATH = Path(__file__).resolve().parent / "ablation_results.json"
REFERENCE = "A_bilinear"
METRIC_KEYS = ("mae", "rmse", "bias")


def fit_predict(frame: pd.DataFrame, fold_col: str, feature_list: list[str]) -> tuple[pd.DataFrame, np.ndarray]:
    train = frame[frame[fold_col] == "train"]
    test = frame[frame[fold_col] == "test"]
    model = fit_tree(train[feature_list].to_numpy(), train["target_value"].to_numpy())
    return test, predict_tree(model, test[feature_list].to_numpy())


def _metrics(variable: str, pred: np.ndarray, y: np.ndarray) -> dict:
    return {**error_metrics(pred, y), "invalid_predictions": invalid_count(variable, pred)}


def evaluate(data: pd.DataFrame, manifest: dict) -> dict:
    for name, feats in VARIANTS.items():
        if set(feats) & FORBIDDEN_FEATURES:
            raise RuntimeError(f"STOP: forbidden feature in {name}")
    if "Mamballi" in set(data["gp_name"]):
        raise RuntimeError("STOP: Mamballi has rows; it must be UNAVAILABLE")

    wide = coarse_wide(data)
    folds_meta = {f["column"]: f for f in manifest["split_methodology"]["folds"]}
    per_fold = {f: {v: {} for v in VARIABLES} for f in FOLD_COLUMNS}
    audits, pooled = {}, {v: {m: ([], []) for m in [REFERENCE] + VARIANT_NAMES} for v in VARIABLES}

    for variable in VARIABLES:
        frame = build_feature_frame(data, variable, wide)
        for fold_col in FOLD_COLUMNS:
            audits.setdefault(fold_col, fold_leakage_audit(frame, fold_col))
            cell = per_fold[fold_col][variable]
            test = frame[frame[fold_col] == "test"]
            y = test["target_value"].to_numpy()
            ref = test["coarse_bilinear_value"].to_numpy()
            cell[REFERENCE] = _metrics(variable, ref, y)
            pooled[variable][REFERENCE][0].append(ref)
            pooled[variable][REFERENCE][1].append(y)
            for name in VARIANT_NAMES:
                test_v, pred = fit_predict(frame, fold_col, VARIANTS[name])
                if not test_v.index.equals(test.index):
                    raise RuntimeError("test rows differ between variants")
                cell[name] = _metrics(variable, pred, y)
                pooled[variable][name][0].append(pred)
                pooled[variable][name][1].append(y)
            cell["n_test_records"] = int(len(test))
            cell["test_gps"] = sorted(test["gp_name"].unique().tolist())
            cell["increments"] = {
                f"{a}->{b}": {k: cell[b][k] - cell[a][k] for k in METRIC_KEYS} | {"feature_group_added": g}
                for a, b, g in INCREMENTS
            }

    aggregate = {}
    for variable in VARIABLES:
        agg = {}
        for m in [REFERENCE] + VARIANT_NAMES:
            vals = {k: [per_fold[f][variable][m][k] for f in FOLD_COLUMNS] for k in METRIC_KEYS}
            p, y = pooled[variable][m]
            pp = np.concatenate(p)
            agg[m] = {
                **{f"{k}_mean_over_folds": float(np.mean(v)) for k, v in vals.items()},
                **{f"{k}_std_over_folds": float(np.std(v, ddof=1)) for k, v in vals.items()},
                "invalid_predictions_total": int(sum(per_fold[f][variable][m]["invalid_predictions"] for f in FOLD_COLUMNS)),
                "row_pooled": _metrics(variable, pp, np.concatenate(y)),
            }
        incs = {}
        for a, b, g in INCREMENTS:
            incs[f"{a}->{b}"] = {
                "feature_group_added": g,
                "fold_mean_delta": {k: agg[b][f"{k}_mean_over_folds"] - agg[a][f"{k}_mean_over_folds"] for k in METRIC_KEYS},
                "pooled_delta": {k: agg[b]["row_pooled"][k] - agg[a]["row_pooled"][k] for k in METRIC_KEYS},
                "per_fold_mae_delta": {f: per_fold[f][variable]["increments"][f"{a}->{b}"]["mae"] for f in FOLD_COLUMNS},
                "folds_with_lower_mae": sum(per_fold[f][variable]["increments"][f"{a}->{b}"]["mae"] < 0 for f in FOLD_COLUMNS),
                "folds_with_higher_mae": sum(per_fold[f][variable]["increments"][f"{a}->{b}"]["mae"] > 0 for f in FOLD_COLUMNS),
            }
        incs[f"{REFERENCE}->C1_coarse_weather"] = {
            "feature_group_added": "nonlinear model on coarse weather (vs direct bilinear value)",
            "fold_mean_delta": {k: agg["C1_coarse_weather"][f"{k}_mean_over_folds"] - agg[REFERENCE][f"{k}_mean_over_folds"]
                                for k in METRIC_KEYS},
            "pooled_delta": {k: agg["C1_coarse_weather"]["row_pooled"][k] - agg[REFERENCE]["row_pooled"][k] for k in METRIC_KEYS},
            "per_fold_mae_delta": {f: per_fold[f][variable]["C1_coarse_weather"]["mae"] - per_fold[f][variable][REFERENCE]["mae"]
                                   for f in FOLD_COLUMNS},
        }
        agg["increments"] = incs
        aggregate[variable] = agg

    return {
        "type": "YelandurMLStage3AFeatureAblation",
        "evaluation_statement": EVALUATION_STATEMENT,
        "spatial_sample_statement": SPATIAL_STATEMENT,
        "effective_spatial_sample_size": "4 ERA5-Land spatial cell groups",
        "row_independence_note": f"The dataset's {len(data):,} rows are NOT independent samples.",
        "dataset": {"file": manifest["dataset_file"], "sha256": manifest.get("dataset_file_sha256"),
                    "row_count": int(len(data))},
        "model_config": CONFIG,
        "model_config_source": "ml_stage2.model.CONFIG (imported unchanged; no tuning)",
        "variants": VARIANTS,
        "increments_definition": [{"from": a, "to": b, "feature_group_added": g} for a, b, g in INCREMENTS],
        "reference": "A_bilinear = coarse_bilinear_value, scored on the same test rows (no training)",
        "error_sign_convention": "bias = mean(prediction - target); delta = later variant minus earlier variant",
        "excluded_from_features": sorted(FORBIDDEN_FEATURES),
        "rainfall_note": "Rainfall processing unchanged; HGB rainfall results are a diagnostic only in this stage.",
        "folds": {
            f: {"held_out_cell_group": folds_meta[f]["held_out_cell_group"], "leakage_audit": audits[f],
                "by_variable": per_fold[f]}
            for f in FOLD_COLUMNS
        },
        "aggregate_by_variable": aggregate,
        "c4_reproduction": c4_reproduction_check(per_fold),
        "stop_condition": "Stage 3A only: no new model, no tuning, no rainfall-specific modelling.",
    }


def c4_reproduction_check(per_fold: dict) -> dict:
    """C4 must equal Stage 2's C_hgb exactly (same config, features, rows)."""
    stage2 = json.loads(STAGE2_RESULTS_PATH.read_text(encoding="utf-8"))
    max_abs, mismatches = 0.0, []
    for f in FOLD_COLUMNS:
        for v in VARIABLES:
            mine = per_fold[f][v]["C4_plus_time_full_C"]
            ref = stage2["folds"][f]["by_variable"][v]["raw"]["C_hgb"]
            for k in ("n", "mae", "rmse", "bias", "invalid_predictions"):
                d = abs(mine[k] - ref[k])
                max_abs = max(max_abs, d)
                if d != 0:
                    mismatches.append(f"{f}/{v}/{k}")
    result = {"compared_against": "research/ml_stage2/stage2_results.json C_hgb (raw)",
              "cells_compared": len(FOLD_COLUMNS) * len(VARIABLES) * 5,
              "max_abs_difference": max_abs, "exact_match": not mismatches, "mismatches": mismatches}
    if mismatches:
        raise RuntimeError(f"STOP: C4 does not reproduce Stage 2 Model C: {mismatches[:5]}")
    return result


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
