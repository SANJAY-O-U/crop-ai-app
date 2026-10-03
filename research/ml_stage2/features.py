"""
Feature construction for ML Stage 2 (Model C).

Every feature for a row at time t comes from (a) the COARSE ERA5 0.25 deg
product at the SAME timestamp t, (b) static GP context, or (c) the timestamp
itself. Nothing is derived from ERA5-Land, the target cell, GP identity, or
fold assignment. The 5 coarse variables are the ERA5 values bilinearly
paired to the row's target cell (`coarse_bilinear_value` in Phase 2D).
"""

import numpy as np
import pandas as pd

from baselines.baseline import FORBIDDEN_FEATURES as STAGE1_FORBIDDEN

VARIABLES = ["temperature_c", "dewpoint_c", "relative_humidity_pct", "rainfall_mm", "wind_speed_kmph"]

COARSE_FEATURES = [f"era5_{v}" for v in VARIABLES]
STATIC_FEATURES = ["elevation_mean_m", "elevation_range_m", "centroid_to_cell_km", "intersecting_cell_count"]
TIME_FEATURES = ["sin_hour", "cos_hour", "sin_day_of_year", "cos_day_of_year"]
FEATURES = COARSE_FEATURES + STATIC_FEATURES + TIME_FEATURES

FORBIDDEN_FEATURES = set(STAGE1_FORBIDDEN) | {
    "coverage_status", "in_primary_population", "taluka_panchayat_lgd_code",
    "centroid_latitude", "centroid_longitude", "local_date_ist", "timestamp_utc",
    "coarse_nearest_latitude", "coarse_nearest_longitude",
}

# Row keys carried alongside the features for scoring/auditing only.
META_COLUMNS = ["gp_name", "cell_group_id", "in_primary_population", "timestamp_utc", "variable",
                "target_value", "coarse_bilinear_value", "coarse_nearest_value",
                "split_fold_1", "split_fold_2", "split_fold_3", "split_fold_4"]


def time_features(timestamps: pd.Series) -> pd.DataFrame:
    """Cyclic encodings of the UTC hour and day-of-year of each row's own
    timestamp (period = that year's length, so 365 or 366 days)."""
    ts = pd.to_datetime(timestamps, utc=True)
    hour_angle = 2 * np.pi * ts.dt.hour / 24.0
    year_len = np.where(ts.dt.is_leap_year, 366.0, 365.0)
    day_angle = 2 * np.pi * (ts.dt.dayofyear - 1) / year_len
    return pd.DataFrame({
        "sin_hour": np.sin(hour_angle), "cos_hour": np.cos(hour_angle),
        "sin_day_of_year": np.sin(day_angle), "cos_day_of_year": np.cos(day_angle),
    }, index=timestamps.index)


def coarse_wide(data: pd.DataFrame) -> pd.DataFrame:
    """One row per (gp_name, timestamp_utc) with the 5 coarse ERA5 variables
    at that same timestamp. gp_name is a JOIN KEY here, never a feature."""
    wide = data.pivot(index=["gp_name", "timestamp_utc"], columns="variable", values="coarse_bilinear_value")
    wide = wide[VARIABLES]
    wide.columns = COARSE_FEATURES
    return wide.reset_index()


def build_feature_frame(data: pd.DataFrame, variable: str, wide: pd.DataFrame | None = None) -> pd.DataFrame:
    """Rows of `variable` with META_COLUMNS + FEATURES. Joins coarse values
    on (gp_name, timestamp_utc) exactly -- same-timestamp only."""
    wide = coarse_wide(data) if wide is None else wide
    rows = data[data["variable"] == variable]
    keep = [c for c in META_COLUMNS if c in rows.columns] + STATIC_FEATURES
    frame = rows[keep].merge(wide, on=["gp_name", "timestamp_utc"], how="left", validate="one_to_one")
    frame = pd.concat([frame, time_features(frame["timestamp_utc"])], axis=1)
    if frame[FEATURES].isna().any().any():
        raise ValueError(f"missing feature values for {variable}")
    return frame
