"""
Rainfall metrics for Stage 3B. A prediction or target is "wet" when it is
> WET_THRESHOLD_MM. Error sign convention: prediction - target.
"""

import numpy as np

from baselines.metrics import error_metrics
from ml_stage3b_rainfall.config import WET_THRESHOLD_MM


def occurrence_metrics(pred_wet: np.ndarray, obs_wet: np.ndarray) -> dict:
    pred_wet = np.asarray(pred_wet, dtype=bool)
    obs_wet = np.asarray(obs_wet, dtype=bool)
    tp = int((pred_wet & obs_wet).sum())
    fp = int((pred_wet & ~obs_wet).sum())
    fn = int((~pred_wet & obs_wet).sum())
    tn = int((~pred_wet & ~obs_wet).sum())
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
    n = len(obs_wet)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": precision, "recall": recall, "f1": f1,
            "observed_wet_fraction": (tp + fn) / n if n else None,
            "predicted_wet_fraction": (tp + fp) / n if n else None}


def _subset(pred, y, mask) -> dict:
    return error_metrics(pred[mask], y[mask]) if mask.any() else {"n": 0, "mae": None, "rmse": None, "bias": None}


def rainfall_metrics(pred: np.ndarray, y: np.ndarray) -> dict:
    """Full metric block for one method's prediction (raw OR constrained)."""
    pred = np.asarray(pred, dtype=float)
    y = np.asarray(y, dtype=float)
    obs_wet = y > WET_THRESHOLD_MM
    pred_wet = pred > WET_THRESHOLD_MM
    dry = ~obs_wet
    return {
        "overall": {**error_metrics(pred, y), "invalid_predictions": int((pred < 0).sum())},
        "occurrence": occurrence_metrics(pred_wet, obs_wet),
        "amount_on_observed_wet_hours": _subset(pred, y, obs_wet),
        "amount_on_hit_hours": _subset(pred, y, obs_wet & pred_wet),
        "dry_hour_behaviour": {
            "n_observed_dry": int(dry.sum()),
            "mae": float(np.mean(np.abs(pred[dry] - y[dry]))) if dry.any() else None,
            "mean_prediction_mm": float(np.mean(pred[dry])) if dry.any() else None,
            "fraction_predicted_exactly_zero": float(np.mean(pred[dry] == 0.0)) if dry.any() else None,
            "fraction_predicted_wet": float(np.mean(pred[dry] > WET_THRESHOLD_MM)) if dry.any() else None,
        },
        "totals": {
            "predicted_total_mm": float(pred.sum()),
            "observed_total_mm": float(y.sum()),
            "ratio_predicted_to_observed": float(pred.sum() / y.sum()) if y.sum() > 0 else None,
            "fraction_predicted_exactly_zero": float(np.mean(pred == 0.0)),
        },
    }
