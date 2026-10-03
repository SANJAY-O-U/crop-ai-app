"""
Frozen configuration of the OFFLINE daily evaluation bridge.

Everything that could influence a conclusion is fixed here, before any result
is computed: the hourly -> daily aggregation rules, the metric/skill
definitions, the evidence rule used to decide "proceed" vs "pass-through",
and the bootstrap settings. Nothing here is tuned on results.

Evaluation against the ERA5-Land reanalysis proxy -- NOT observation -- unless
a section says it uses station observations.
"""

# --- input -------------------------------------------------------------------
DATASET = "data/training/yelandur_multi_gp.parquet"          # Phase 2D, frozen (SHA-256 recorded per run)
DATASET_MANIFEST = "research/multi_gp/yelandur_multi_gp_manifest.json"
FOLD_COLUMNS = ["split_fold_1", "split_fold_2", "split_fold_3", "split_fold_4"]  # Phase 2D folds, unchanged
DAY_COLUMN = "local_date_ist"        # Phase 2D local calendar day (IST = UTC+05:30)
HOURS_PER_DAY = 24                   # a day is valid for a variable only with ALL 24 hourly values

# --- hourly -> daily rules (mirrors Open-Meteo's daily definitions used by the live API) ---------
# daily field (API name) : hourly research variable, aggregation, unit
AGGREGATION = {
    "temperature_max_c": {"hourly": "temperature_c",         "agg": "max",  "unit": "degC", "open_meteo": "temperature_2m_max"},
    "temperature_min_c": {"hourly": "temperature_c",         "agg": "min",  "unit": "degC", "open_meteo": "temperature_2m_min"},
    "rainfall_mm":       {"hourly": "rainfall_mm",           "agg": "sum",  "unit": "mm",   "open_meteo": "precipitation_sum"},
    "humidity_pct":      {"hourly": "relative_humidity_pct", "agg": "mean", "unit": "%",    "open_meteo": "relative_humidity_2m_mean"},
    "wind_kmph":         {"hourly": "wind_speed_kmph",       "agg": "max",  "unit": "km/h", "open_meteo": "windspeed_10m_max"},
}
DAILY_VARIABLES = list(AGGREGATION)
HOURLY_FOR_CANDIDATE = ["temperature_c", "relative_humidity_pct", "rainfall_mm", "wind_speed_kmph"]
PHYSICAL_BOUNDS = {"rainfall_mm": (0.0, None), "wind_kmph": (0.0, None), "humidity_pct": (0.0, 100.0)}

# --- methods ---------------------------------------------------------------------
BLOCK = "block_as_is"
PRODUCTION = "production_baseline"
OFFSET = "block_plus_train_bias"   # diagnostic baseline: block + constant mean(target - block) of the fold's TRAIN days
CANDIDATES = ["C_daily_hgb", "R_daily_ridge", "C_hourly_agg"]
RIDGE_ALPHA = 1.0                    # Stage 1 value, fixed a priori
DAILY_FEATURES = ["block_temperature_max_c", "block_temperature_min_c", "block_rainfall_mm",
                  "block_humidity_pct", "block_wind_kmph",
                  "elevation_mean_m", "elevation_range_m", "elevation_delta_m",
                  "sin_day_of_year", "cos_day_of_year"]

# --- skill / evidence rules ---------------------------------------------------------
SKILL_ZERO_TOLERANCE = 0.01          # |skill| <= 0.01 is labelled "zero" (the number is always reported too)
BOOTSTRAP = {"reps": 2000, "block_days": 7, "seed": 20260101}
EVIDENCE_RULE = {
    "pooled_mae_skill_vs_block_gt": SKILL_ZERO_TOLERANCE,
    "pooled_rmse_skill_vs_block_gt": SKILL_ZERO_TOLERANCE,
    "min_folds_mae_positive_of_4": 3,
    "min_quarters_mae_positive_of_4": 3,
    "bootstrap_ci_lower_mae_skill_gt": 0.0,
    "must_beat_production_baseline_mae": True,
    "rainfall_default": "pass_through",   # rainfall stays pass-through unless EVERY criterion above holds
}

# --- observation diagnostic (Stage 5 data; independent of the ERA5-Land proxy) --------------
OBS_MIN_MATCHED_HOURS_PER_DAY = 6    # matched obs hours needed for a station-day statistic
