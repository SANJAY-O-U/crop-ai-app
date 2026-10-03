"""
Error metrics for the ML Stage 1 baselines. Pure numpy.

Sign convention: error = prediction - target, so a positive `bias` means the
prediction is on average HIGHER than the ERA5-Land reanalysis-proxy target.
"""

import numpy as np


def error_metrics(prediction, target) -> dict:
    prediction = np.asarray(prediction, dtype=float)
    target = np.asarray(target, dtype=float)
    if prediction.shape != target.shape:
        raise ValueError("prediction and target must have the same shape")
    if np.isnan(prediction).any() or np.isnan(target).any():
        raise ValueError("NaN in prediction or target -- missing rows must be excluded before scoring")
    n = int(prediction.size)
    if n == 0:
        return {"n": 0, "mae": None, "rmse": None, "bias": None}
    err = prediction - target
    return {
        "n": n,
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err ** 2))),
        "bias": float(np.mean(err)),
    }
