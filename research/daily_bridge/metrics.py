"""Error metrics, skill scores, labels and a day-block bootstrap. Pure numpy."""

import numpy as np

from daily_bridge import config


def error_metrics(pred, target) -> dict:
    """error = prediction - target (positive bias = over-prediction). NaN pairs are rejected by the caller."""
    pred, target = np.asarray(pred, float), np.asarray(target, float)
    ok = ~(np.isnan(pred) | np.isnan(target))
    n = int(ok.sum())
    if n == 0:
        return {"n": 0, "mae": None, "rmse": None, "bias": None}
    e = pred[ok] - target[ok]
    return {"n": n, "mae": float(np.abs(e).mean()), "rmse": float(np.sqrt((e ** 2).mean())), "bias": float(e.mean())}


def skill(candidate_error, reference_error):
    """skill = 1 - candidate_error / reference_error. Undefined (None) when the reference error is 0/None.
    Positive: candidate better than reference. 0: same. Negative: worse."""
    if candidate_error is None or reference_error is None or reference_error == 0:
        return None
    return 1.0 - candidate_error / reference_error


def skill_scores(cand: dict, ref: dict) -> dict:
    """MAE and RMSE skill; bias skill uses |bias| (sign of bias is not an error magnitude)."""
    ab = lambda m: None if m["bias"] is None else abs(m["bias"])
    return {"mae": skill(cand["mae"], ref["mae"]), "rmse": skill(cand["rmse"], ref["rmse"]),
            "abs_bias": skill(ab(cand), ab(ref))}


def skill_label(value, tolerance: float = config.SKILL_ZERO_TOLERANCE) -> str:
    if value is None:
        return "undefined"
    if value > tolerance:
        return "positive"
    if value < -tolerance:
        return "negative"
    return "zero"


def bootstrap_skill(day_codes, pred_cand, pred_ref, target, reps=None, block_days=None, seed=None) -> dict:
    """Moving-block (circular) bootstrap over calendar days of the pooled MAE/RMSE skill of
    `pred_cand` relative to `pred_ref`. Rows sharing a day move together (spatial dependence)."""
    cfg = config.BOOTSTRAP
    reps, block_days, seed = reps or cfg["reps"], block_days or cfg["block_days"], cfg["seed"] if seed is None else seed
    day_codes = np.asarray(day_codes)
    uniq, inv = np.unique(day_codes, return_inverse=True)
    D = len(uniq)
    target = np.asarray(target, float)
    ec, er = np.asarray(pred_cand, float) - target, np.asarray(pred_ref, float) - target
    cnt = np.bincount(inv, minlength=D).astype(float)
    s = {k: np.bincount(inv, weights=w, minlength=D) for k, w in
         {"ac": np.abs(ec), "ar": np.abs(er), "qc": ec ** 2, "qr": er ** 2}.items()}
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(D / block_days))
    starts = rng.integers(0, D, size=(reps, nb))
    idx = ((starts[:, :, None] + np.arange(block_days)[None, None, :]) % D).reshape(reps, -1)[:, :D]
    n = cnt[idx].sum(1)
    mae_c, mae_r = s["ac"][idx].sum(1) / n, s["ar"][idx].sum(1) / n
    rmse_c, rmse_r = np.sqrt(s["qc"][idx].sum(1) / n), np.sqrt(s["qr"][idx].sum(1) / n)
    out = {}
    for name, sk in (("mae", 1 - mae_c / mae_r), ("rmse", 1 - rmse_c / rmse_r)):
        lo, hi = np.percentile(sk, [2.5, 97.5])
        out[name] = {"ci95": [float(lo), float(hi)]}
    out.update(reps=reps, block_days=block_days, n_days=int(D), seed=seed)
    return out
