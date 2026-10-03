"""
Stage 5 metrics and dependence-aware uncertainty.

Paired differences use |e_C4| - |e_baseline| per matched hour. Uncertainty
is a moving-block bootstrap over DAYS within each station (block = 7 days),
so autocorrelated hours are not treated as independent; pooled intervals
resample each station separately and never mix station time series.
"""

import numpy as np
import pandas as pd

from stage5_observational_validation import criteria5


def point_metrics(pred: np.ndarray, obs: np.ndarray) -> dict:
    e = np.asarray(pred, float) - np.asarray(obs, float)
    if len(e) == 0:
        return {"n": 0, "mae": None, "rmse": None, "bias": None, "median_abs_error": None}
    return {"n": int(len(e)), "mae": float(np.mean(np.abs(e))), "rmse": float(np.sqrt(np.mean(e ** 2))),
            "bias": float(np.mean(e)), "median_abs_error": float(np.median(np.abs(e)))}


def rain_metrics(pred: np.ndarray, obs: np.ndarray, period_h: np.ndarray) -> dict:
    pred, obs, period_h = map(lambda a: np.asarray(a, float), (pred, obs, period_h))
    base = point_metrics(pred, obs)
    thr = criteria5.RAIN_WET_THRESHOLD_MM_PER_H * period_h
    wet_o, wet_p = obs > thr, pred > thr
    dry = ~wet_o
    base.update({
        "wet_periods_observed": int(wet_o.sum()),
        "wet_period_mae": float(np.mean(np.abs(pred[wet_o] - obs[wet_o]))) if wet_o.any() else None,
        "dry_period_mae": float(np.mean(np.abs(pred[dry] - obs[dry]))) if dry.any() else None,
        "false_wet_rate": float(np.mean(wet_p[dry])) if dry.any() else None,
        "hit_rate": float(np.mean(wet_p[wet_o])) if wet_o.any() else None,
        "total_ratio_pred_to_obs": float(pred.sum() / obs.sum()) if obs.sum() > 0 else None,
        "negative_predictions": int((pred < 0).sum()),
    })
    return base


def _block_indices(days: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Row indices of one moving-block bootstrap replicate over days."""
    uniq = np.unique(days)
    n = len(uniq)
    b = min(criteria5.BOOTSTRAP_BLOCK_DAYS, n)
    starts = rng.integers(0, n - b + 1, size=int(np.ceil(n / b)))
    chosen = np.concatenate([uniq[s:s + b] for s in starts])[:n]
    pos = {d: np.flatnonzero(days == d) for d in uniq}
    return np.concatenate([pos[d] for d in chosen])


def _prepare_days(days) -> tuple[np.ndarray, np.ndarray, int]:
    """Integer day codes -> (row order grouped by day, day boundaries, n_days).
    Works for any label type (naive, tz-aware, object) because grouping uses
    pd.factorize(sort=True), whose day order equals np.unique's. Built ONCE
    per station instead of once per bootstrap replicate."""
    codes, uniques = pd.factorize(pd.Series(days), sort=True)
    n = len(uniques)
    order = np.argsort(codes, kind="stable")  # stable: rows stay in ascending index order within a day
    bounds = np.searchsorted(codes[order], np.arange(n + 1))
    return order, bounds, n


def _block_indices_prepared(prep: tuple[np.ndarray, np.ndarray, int], rng: np.random.Generator) -> np.ndarray:
    """Same selection (and the same random draws) as _block_indices, from prepared groups."""
    order, bounds, n = prep
    b = min(criteria5.BOOTSTRAP_BLOCK_DAYS, n)
    starts = rng.integers(0, n - b + 1, size=int(np.ceil(n / b)))
    chosen = np.concatenate([np.arange(s, s + b) for s in starts])[:n]
    return np.concatenate([order[bounds[d]:bounds[d + 1]] for d in chosen])


def paired_bootstrap(groups: list[tuple[np.ndarray, np.ndarray]], reps: int = criteria5.BOOTSTRAP_REPLICATES,
                     seed: int = criteria5.BOOTSTRAP_SEED) -> dict:
    """groups: [(diff_per_hour, day_label_per_hour), ...] one per station.
    Returns the pooled mean difference and a 95% percentile interval."""
    groups = [(np.asarray(d, float), k) for d, k in groups if len(d)]
    if not groups:
        return {"mean_diff": None, "ci95": None, "n_hours": 0, "n_stations": 0}
    prepared = [(d, _prepare_days(k)) for d, k in groups]
    total_n = sum(len(d) for d, _ in prepared)
    point = float(sum(d.sum() for d, _ in prepared) / total_n)
    rng = np.random.default_rng(seed)
    stats = np.empty(reps)
    for r in range(reps):
        s, n = 0.0, 0
        for d, prep in prepared:
            idx = _block_indices_prepared(prep, rng)
            s += d[idx].sum()
            n += len(idx)
        stats[r] = s / n
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return {"mean_diff": point, "ci95": [float(lo), float(hi)], "n_hours": int(total_n), "n_stations": len(prepared),
            "interval_excludes_zero": bool(lo > 0 or hi < 0),
            "method": f"moving-block bootstrap over days (block {criteria5.BOOTSTRAP_BLOCK_DAYS} d), within station, "
                      f"{reps} replicates, seed {seed}"}


def season_of(ts: pd.Series) -> pd.Series:
    m = ts.dt.month
    out = pd.Series(index=ts.index, dtype=object)
    for name, months in criteria5.SEASONS.items():
        out[m.isin(months)] = name
    return out
