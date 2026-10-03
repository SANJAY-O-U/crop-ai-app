"""
Stage 4D metrics. Reuses the frozen metric definitions:
  baselines.metrics.error_metrics          MAE / RMSE / bias (prediction - target) / n
  ml_stage2.evaluation.invalid_count       rainfall<0, RH outside 0-100, wind<0
  ml_stage3b_rainfall.metrics.rainfall_metrics  wet-hour behaviour (wet = > 0.1 mm)
Pooled metrics are accumulated exactly (sums), not approximated.
"""

import hashlib

import numpy as np

from baselines.metrics import error_metrics
from ml_stage2.evaluation import invalid_count
from ml_stage3b_rainfall.metrics import rainfall_metrics

UNITS = {"temperature_c": "degC", "dewpoint_c": "degC", "relative_humidity_pct": "%",
         "rainfall_mm": "mm/hour", "wind_speed_kmph": "km/h"}


def prediction_hash(pred: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(pred, dtype=np.float64).tobytes()).hexdigest()


def summarize(pred: np.ndarray, y: np.ndarray, variable: str) -> dict:
    out = {**error_metrics(pred, y), "invalid_predictions": invalid_count(variable, pred),
           "unit": UNITS[variable], "prediction_sha256": prediction_hash(pred)}
    if variable == "rainfall_mm":
        rm = rainfall_metrics(pred, y)
        out["rainfall"] = {k: rm[k] for k in ("occurrence", "amount_on_observed_wet_hours", "dry_hour_behaviour", "totals")}
    return out


class Pooled:
    """Exact pooled MAE/RMSE/bias accumulator across folds."""

    def __init__(self):
        self.n = 0
        self.abs = 0.0
        self.sq = 0.0
        self.err = 0.0
        self.invalid = 0
        self._rain = ([], [])

    def add(self, pred: np.ndarray, y: np.ndarray, variable: str) -> None:
        e = pred - y
        self.n += len(e)
        self.abs += float(np.abs(e).sum())
        self.sq += float((e ** 2).sum())
        self.err += float(e.sum())
        self.invalid += invalid_count(variable, pred)
        if variable == "rainfall_mm":
            self._rain[0].append(pred)
            self._rain[1].append(y)

    def result(self, variable: str) -> dict:
        out = {"n": self.n, "mae": self.abs / self.n, "rmse": (self.sq / self.n) ** 0.5, "bias": self.err / self.n,
               "invalid_predictions": self.invalid, "unit": UNITS[variable]}
        if variable == "rainfall_mm" and self._rain[0]:
            rm = rainfall_metrics(np.concatenate(self._rain[0]), np.concatenate(self._rain[1]))
            out["rainfall"] = {k: rm[k] for k in ("occurrence", "amount_on_observed_wet_hours", "dry_hour_behaviour", "totals")}
        return out


def fold_mean_std(per_fold: list[dict]) -> dict:
    out = {}
    for k in ("mae", "rmse", "bias"):
        vals = np.array([f[k] for f in per_fold], dtype=float)
        out[f"{k}_mean"] = float(vals.mean())
        out[f"{k}_std"] = float(vals.std(ddof=1)) if len(vals) > 1 else None
    out["n_folds"] = len(per_fold)
    out["invalid_predictions_total"] = int(sum(f["invalid_predictions"] for f in per_fold))
    return out
