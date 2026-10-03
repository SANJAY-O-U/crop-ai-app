"""
Two-stage precipitation model (S_two_stage):

    p(wet)  = HistGradientBoostingClassifier(features)      -- all training hours
    amount  = HistGradientBoostingRegressor(poisson)(features) -- wet training hours only
    raw prediction = amount  if p(wet) >= threshold  else 0.0

Threshold selection uses the fold's TRAINING rows only (see config.py).
Features are Stage 2 Model C's 13 features (ml_stage2.features.FEATURES).
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

from ml_stage2.features import FEATURES
from ml_stage3b_rainfall.config import (
    AMOUNT_CONFIG, CLASSIFIER_CONFIG, INNER_TRAIN_END_EXCLUSIVE, INNER_VAL_START, THRESHOLD_GRID, WET_THRESHOLD_MM,
)


def wet_labels(target) -> np.ndarray:
    return (np.asarray(target, dtype=float) > WET_THRESHOLD_MM).astype(int)


def fit_classifier(X, y) -> HistGradientBoostingClassifier:
    y = np.asarray(y, dtype=int)
    if len(np.unique(y)) < 2:
        raise ValueError("classifier training data has a single class")
    return HistGradientBoostingClassifier(**CLASSIFIER_CONFIG).fit(np.asarray(X, dtype=float), y)


def wet_probability(clf, X) -> np.ndarray:
    return clf.predict_proba(np.asarray(X, dtype=float))[:, list(clf.classes_).index(1)]


def fit_amount(X, y) -> HistGradientBoostingRegressor:
    y = np.asarray(y, dtype=float)
    if (y <= WET_THRESHOLD_MM).any():
        raise ValueError("amount model must be trained on wet hours only")
    return HistGradientBoostingRegressor(**AMOUNT_CONFIG).fit(np.asarray(X, dtype=float), y)


def f1_at(prob: np.ndarray, labels: np.ndarray, threshold: float) -> float:
    pred = prob >= threshold
    tp = int((pred & (labels == 1)).sum())
    fp = int((pred & (labels == 0)).sum())
    fn = int((~pred & (labels == 1)).sum())
    return 0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn)


def choose_threshold(curve: dict[float, float]) -> tuple[float, float]:
    """Highest F1; ties -> lowest threshold."""
    best = max(curve.values())
    return min(t for t, f in curve.items() if f == best), best


def inner_split(train: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    inner_train = train[train["timestamp_utc"] < INNER_TRAIN_END_EXCLUSIVE]
    inner_val = train[train["timestamp_utc"] >= INNER_VAL_START]
    return inner_train, inner_val


def select_threshold(train: pd.DataFrame) -> dict:
    """Receives ONLY the fold's training rows. Returns the selected
    threshold plus the inner-validation F1 curve for the record."""
    inner_train, inner_val = inner_split(train)
    if inner_train.empty or inner_val.empty:
        raise ValueError("inner temporal split is empty")
    clf = fit_classifier(inner_train[FEATURES].to_numpy(), wet_labels(inner_train["target_value"]))
    prob = wet_probability(clf, inner_val[FEATURES].to_numpy())
    labels = wet_labels(inner_val["target_value"])
    curve = {t: f1_at(prob, labels, t) for t in THRESHOLD_GRID}
    threshold, best = choose_threshold(curve)
    return {
        "threshold": threshold,
        "inner_val_f1": best,
        "inner_train_rows": int(len(inner_train)),
        "inner_val_rows": int(len(inner_val)),
        "inner_train_range_utc": [str(inner_train["timestamp_utc"].min()), str(inner_train["timestamp_utc"].max())],
        "inner_val_range_utc": [str(inner_val["timestamp_utc"].min()), str(inner_val["timestamp_utc"].max())],
        "f1_curve": {str(t): f for t, f in curve.items()},
    }


def fit_two_stage(train: pd.DataFrame) -> dict:
    selection = select_threshold(train)
    clf = fit_classifier(train[FEATURES].to_numpy(), wet_labels(train["target_value"]))
    wet = train[train["target_value"] > WET_THRESHOLD_MM]
    amount = fit_amount(wet[FEATURES].to_numpy(), wet["target_value"].to_numpy())
    return {"classifier": clf, "amount": amount, "selection": selection,
            "n_train": int(len(train)), "n_train_wet": int(len(wet))}


def predict_two_stage(fitted: dict, X) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(raw prediction, p(wet), predicted-wet mask)."""
    X = np.asarray(X, dtype=float)
    prob = wet_probability(fitted["classifier"], X)
    is_wet = prob >= fitted["selection"]["threshold"]
    amount = fitted["amount"].predict(X)
    return np.where(is_wet, amount, 0.0), prob, is_wet
