"""OFFLINE research correction candidates. Nothing here is deployable or saved.

C_daily_hgb   : the Stage 2 HistGradientBoosting configuration (ml_stage2.model.CONFIG, unchanged), fitted on DAILY features
                available at the production grain (block daily values + Panchayat elevation + day of year).
R_daily_ridge : the Stage 1 ridge definition (alpha 1.0, train-only standardisation) on the same daily features.
C_hourly_agg  : the Stage 3A 'C4' hourly model (unchanged features/config), predictions aggregated to daily with the
                same rules. REFERENCE ONLY: it needs hourly coarse inputs that the live daily API does not provide.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from daily_bridge import aggregate, config
from ml_stage2 import features as s2_features
from ml_stage2 import model as s2_model


def day_of_year_features(dates: pd.Series) -> pd.DataFrame:
    ts = pd.to_datetime(dates)
    year_len = np.where(ts.dt.is_leap_year, 366.0, 365.0)
    ang = 2 * np.pi * (ts.dt.dayofyear - 1) / year_len
    return pd.DataFrame({"sin_day_of_year": np.sin(ang), "cos_day_of_year": np.cos(ang)}, index=dates.index)


def fit_predict_daily(train: pd.DataFrame, test: pd.DataFrame, target_col: str) -> dict:
    """Return {method: predictions for test rows}. Rows with NaN features/target are the caller's responsibility."""
    X_tr, y_tr = train[config.DAILY_FEATURES].to_numpy(float), train[target_col].to_numpy(float)
    X_te = test[config.DAILY_FEATURES].to_numpy(float)
    hgb = s2_model.fit_tree(X_tr, y_tr)
    scaler = StandardScaler().fit(X_tr)                      # train rows only
    ridge = Ridge(alpha=config.RIDGE_ALPHA).fit(scaler.transform(X_tr), y_tr)
    return {"C_daily_hgb": s2_model.predict_tree(hgb, X_te), "R_daily_ridge": ridge.predict(scaler.transform(X_te))}


def clip_physical(daily_var: str, values):
    lo_hi = config.PHYSICAL_BOUNDS.get(daily_var)
    if not lo_hi:
        return values
    lo, hi = lo_hi
    return np.clip(values, lo, hi)


def hourly_candidate_daily(data: pd.DataFrame, fold_col: str, test_gps: list[str]) -> pd.DataFrame:
    """Fit the C4 hourly model per hourly variable on the fold's 'train' rows, predict the 'test' rows of `test_gps`,
    clip to physical bounds, and aggregate to daily with the same rules. Returns daily rows (gp_name, day, daily vars)."""
    wide = s2_features.coarse_wide(data)
    hourly_pred = []
    for v in config.HOURLY_FOR_CANDIDATE:
        frame = s2_features.build_feature_frame(data, v, wide)
        train = frame[(frame[fold_col] == "train") & frame["target_value"].notna()]
        test = frame[(frame[fold_col] == "test") & frame["gp_name"].isin(test_gps)]
        m = s2_model.fit_tree(train[s2_features.FEATURES].to_numpy(float), train["target_value"].to_numpy(float))
        pred = s2_model.predict_tree(m, test[s2_features.FEATURES].to_numpy(float))
        out = test[["gp_name", "timestamp_utc"]].copy()
        out[v] = pred
        hourly_pred.append(out)
    merged = hourly_pred[0]
    for h in hourly_pred[1:]:
        merged = merged.merge(h, on=["gp_name", "timestamp_utc"], how="outer")
    days = data[["gp_name", "timestamp_utc", config.DAY_COLUMN]].drop_duplicates()
    merged = merged.merge(days, on=["gp_name", "timestamp_utc"], how="left")
    hourly_bounds = {"rainfall_mm": "rainfall_mm", "wind_speed_kmph": "wind_kmph", "relative_humidity_pct": "humidity_pct"}
    for hv, dv in hourly_bounds.items():
        merged[hv] = clip_physical(dv, merged[hv].to_numpy(float))
    return aggregate.to_daily(merged, ["gp_name"])
