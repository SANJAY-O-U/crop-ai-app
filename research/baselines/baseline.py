"""
ML Stage 1 baselines for the Phase 2D Yelandur multi-GP dataset.

BASELINE A -- direct coarse baseline (no training):
    prediction = ERA5 0.25 deg value paired to the ERA5-Land target cell
      A_bilinear: coarse_bilinear_value
      A_nearest : coarse_nearest_value (transparency only)

BASELINE B -- context-aware ridge regression, fit per (fold, variable):
    target_value ~ coarse_bilinear_value + elevation_mean_m + elevation_range_m
                   + centroid_to_cell_km + intersecting_cell_count
    Closed-form ridge on features standardized with TRAINING-row statistics
    only. Intercept = training-row target mean (not penalized). Fixed
    RIDGE_ALPHA chosen a priori -- no hyperparameter search.

Both are evaluated against the ERA5-Land reanalysis proxy -- not observation.
"""

import numpy as np

FEATURES = [
    "coarse_bilinear_value",
    "elevation_mean_m",
    "elevation_range_m",
    "centroid_to_cell_km",
    "intersecting_cell_count",
]

TARGET = "target_value"

# Columns that must never be model inputs: the target itself, anything
# derived from the target cells, and target-cell / group identity.
FORBIDDEN_FEATURES = {
    "target_value", "area_weighted_value", "target_missing_reason",
    "target_rainfall_clamped", "area_weighted_rainfall_clamped",
    "cell_group_id", "target_cell_latitude", "target_cell_longitude",
    "cell_group_complete_gp_count", "area_weighted_cell_count",
    "panchayat_lgd_code", "gp_name", "target_source_file", "target_source_sha256",
    "split_fold_1", "split_fold_2", "split_fold_3", "split_fold_4", "temporal_period",
}

# Fixed a priori, not tuned: with O(1e5) training rows per fit on
# standardized features it only guards against exact collinearity among the
# GP-constant static features.
RIDGE_ALPHA = 1.0


def fit_standardizer(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Column means/stds from the rows given (training rows only). A
    zero-variance column gets std=1 so it standardizes to all zeros."""
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std = np.where(std > 0, std, 1.0)
    return mean, std


def fit_ridge(X_train: np.ndarray, y_train: np.ndarray, alpha: float = RIDGE_ALPHA) -> dict:
    X_train = np.asarray(X_train, dtype=float)
    y_train = np.asarray(y_train, dtype=float)
    if np.isnan(X_train).any() or np.isnan(y_train).any():
        raise ValueError("NaN in training data")
    mean, std = fit_standardizer(X_train)
    Z = (X_train - mean) / std
    y_mean = float(y_train.mean())
    A = Z.T @ Z + alpha * np.eye(Z.shape[1])
    coef = np.linalg.solve(A, Z.T @ (y_train - y_mean))
    return {"feature_mean": mean, "feature_std": std, "coef_standardized": coef,
            "intercept": y_mean, "alpha": alpha, "n_train": int(len(y_train))}


def predict_ridge(model: dict, X: np.ndarray) -> np.ndarray:
    Z = (np.asarray(X, dtype=float) - model["feature_mean"]) / model["feature_std"]
    return model["intercept"] + Z @ model["coef_standardized"]


def model_summary(model: dict) -> dict:
    """JSON-safe, human-readable coefficients (standardized and in original
    feature units). This is the only 'model artifact' kept."""
    raw = model["coef_standardized"] / model["feature_std"]
    return {
        "alpha": model["alpha"],
        "n_train": model["n_train"],
        "intercept_at_training_feature_means": model["intercept"],
        "coef_standardized": dict(zip(FEATURES, map(float, model["coef_standardized"]))),
        "coef_per_original_unit": dict(zip(FEATURES, map(float, raw))),
        "training_feature_mean": dict(zip(FEATURES, map(float, model["feature_mean"]))),
        "training_feature_std": dict(zip(FEATURES, map(float, model["feature_std"]))),
    }
