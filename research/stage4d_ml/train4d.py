"""
Stage 4D models, all FROZEN configurations from earlier stages (imported,
not copied or re-tuned):

  A1_bilinear  ERA5 0.25 deg bilinear value of the target variable (no training)
  A2_nearest   ERA5 0.25 deg nearest-point value (no training)
  B_ridge      Stage 1 ridge (baselines.baseline.fit_ridge, alpha=1.0), features =
               Stage 1 list with `coarse_bilinear_value` -> `era5_<variable>`
  C1..C4       Stage 2 HistGradientBoostingRegressor (ml_stage2.model.CONFIG) on
               the Stage 3A ablation feature lists (ml_stage3_ablation.variants)

Fitting uses only the rows of the fold's training mask. Ridge
standardization statistics come from those rows only (fit_ridge). Trees use
no external preprocessing; sklearn's binning is fit inside .fit().
"""

import numpy as np

from baselines.baseline import FEATURES as STAGE1_FEATURES
from baselines.baseline import RIDGE_ALPHA, fit_ridge, predict_ridge
from ml_stage2.model import CONFIG as HGB_CONFIG
from ml_stage2.model import fit_tree, predict_tree
from ml_stage3_ablation.variants import VARIANTS
from stage4d_ml.leakage_checks import verify_feature_matrix

C_VARIANTS = {"C1": VARIANTS["C1_coarse_weather"], "C2": VARIANTS["C2_plus_elevation"],
              "C3": VARIANTS["C3_plus_spatial"], "C4": VARIANTS["C4_plus_time_full_C"]}
METHODS = ["A1_bilinear", "A2_nearest", "B_ridge", "C1", "C2", "C3", "C4"]


def b_features(variable: str) -> list[str]:
    return [f"era5_{variable}" if f == "coarse_bilinear_value" else f for f in STAGE1_FEATURES]


def feature_lists(variable: str) -> dict[str, list[str]]:
    return {"B_ridge": b_features(variable), **{k: list(v) for k, v in C_VARIANTS.items()}}


def _X(frame, rows: np.ndarray, feats: list[str]) -> np.ndarray:
    X = frame.loc[rows, feats].to_numpy(dtype=float)
    verify_feature_matrix(X, feats)
    return X


def fit_and_predict(wide, train: np.ndarray, test: np.ndarray, variable: str, methods=METHODS,
                    references: dict | None = None) -> tuple[dict, dict, dict]:
    """Returns (predictions on `test`, predictions on each reference frame's
    rows, fitted-model summaries). `references` maps name -> (frame, mask)."""
    references = references or {}
    y_train = wide.loc[train, f"target_{variable}"].to_numpy(dtype=float)
    preds, ref_preds, info = {}, {name: {} for name in references}, {}
    for m in methods:
        if m == "A1_bilinear":
            preds[m] = wide.loc[test, f"era5_{variable}"].to_numpy(dtype=float)
            for name, (frame, mask) in references.items():
                ref_preds[name][m] = frame.loc[mask, f"era5_{variable}"].to_numpy(dtype=float)
        elif m == "A2_nearest":
            preds[m] = wide.loc[test, f"nearest_{variable}"].to_numpy(dtype=float)
            for name, (frame, mask) in references.items():
                ref_preds[name][m] = frame.loc[mask, f"nearest_{variable}"].to_numpy(dtype=float)
        elif m == "B_ridge":
            feats = b_features(variable)
            model = fit_ridge(_X(wide, train, feats), y_train)
            preds[m] = predict_ridge(model, _X(wide, test, feats))
            for name, (frame, mask) in references.items():
                ref_preds[name][m] = predict_ridge(model, _X(frame, mask, feats))
            info[m] = {"alpha": model["alpha"], "n_train": model["n_train"],
                       "coef_standardized": dict(zip(feats, map(float, model["coef_standardized"]))),
                       "intercept": model["intercept"]}
        else:
            feats = C_VARIANTS[m]
            model = fit_tree(_X(wide, train, feats), y_train)
            preds[m] = predict_tree(model, _X(wide, test, feats))
            for name, (frame, mask) in references.items():
                ref_preds[name][m] = predict_tree(model, _X(frame, mask, feats))
            info[m] = {"n_iter": int(model.n_iter_), "n_train": int(train.sum()), "n_features": len(feats)}
    return preds, ref_preds, info


def model_configuration() -> dict:
    return {"A1_bilinear": "ERA5 bilinear value of the target variable; no training",
            "A2_nearest": "ERA5 nearest-point value of the target variable; no training",
            "B_ridge": {"source": "baselines.baseline (Stage 1)", "alpha": RIDGE_ALPHA,
                        "features": "Stage 1 FEATURES with coarse_bilinear_value -> era5_<variable>",
                        "standardization": "fit on training rows only"},
            "C1..C4": {"source": "ml_stage2.model.CONFIG (Stage 2) + ml_stage3_ablation.variants (Stage 3A)",
                       "hgb_config": HGB_CONFIG, "variants": C_VARIANTS}}
