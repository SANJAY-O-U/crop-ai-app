# ML Stage 2 — first nonlinear model (Yelandur multi-GP)

**Evaluation against ERA5-Land reanalysis proxy — not observation.**

Reanalysis-to-reanalysis spatial transfer: ERA5 0.25° coarse inputs +
static GP context → ERA5-Land 0.1° nearest-cell reanalysis proxy.

> The effective spatial sample comprises 4 ERA5-Land cell groups, so these
> results are exploratory and do not establish generalized Panchayat-level
> forecasting skill.

## Model C

`sklearn.ensemble.HistGradientBoostingRegressor`, one model per
fold × target variable (4 × 5 = 20 fits), with one configuration fixed
before any Stage 2 result was computed (`model.CONFIG`):

| Parameter | Value | Why |
|---|---|---|
| `loss` | `squared_error` | same objective family as the RMSE reported |
| `learning_rate` | 0.1 | sklearn default |
| `max_iter` | 200 | fixed number of boosting rounds |
| `max_leaf_nodes` | 31 | sklearn default |
| `min_samples_leaf` | 200 | each leaf summarizes ≥ 200 training hours |
| `l2_regularization` | 0.0 | sklearn default |
| `max_bins` | 255 | sklearn default |
| `early_stopping` | `False` | sklearn's early stopping uses a *random* validation split of training rows |
| `random_state` | 0 | determinism |

No hyperparameter search. No input scaling (trees are scale-invariant);
sklearn's internal feature binning is fit inside `.fit()` on training rows
only. No model file is written.

## Features (13)

| Group | Features |
|---|---|
| Coarse ERA5, same timestamp | `era5_temperature_c`, `era5_dewpoint_c`, `era5_relative_humidity_pct`, `era5_rainfall_mm`, `era5_wind_speed_kmph` (bilinear pairing to the target cell) |
| Static GP context | `elevation_mean_m`, `elevation_range_m`, `centroid_to_cell_km`, `intersecting_cell_count` |
| Time (UTC, cyclic) | `sin_hour`, `cos_hour`, `sin_day_of_year`, `cos_day_of_year` |

Never used: ERA5-Land target values, the area-weighted diagnostic,
target-cell coordinates, `cell_group_id`, GP identity, fold columns, other
timestamps' values, or anything derived from ERA5-Land
(`features.FORBIDDEN_FEATURES`).

## Comparison methods

A_bilinear, A_nearest and B_ridge are recomputed with the **unchanged**
Stage 1 code on the same test rows (a test checks they match
`research/baselines/baseline_results.json` exactly). Stage 1 results are
not modified.

## Physical bounds

Raw predictions are scored first and are the primary result. Invalid raw
predictions are counted (rainfall < 0, RH < 0 or > 100, wind < 0).
Separately, a **post-processing diagnostic** clips rainfall and wind at 0
and RH to 0–100 for every method; it never replaces the raw results.

## Splits and population

The exact Phase 2D folds: leave-one-ERA5-Land-cell-group-out (4 folds),
train 2021-01-01 – 2022-12-24 UTC, 7-day embargo, test 2023. Agara
(PARTIAL) is excluded; Mamballi (UNAVAILABLE) has no rows. Rainfall
processing is unchanged from Phase 2D (11 missing first-hour rows; 5,001
clamped steps of at most ~0.000034 mm).

## Run

```bash
python research/ml_stage2/evaluation.py
```

Writes `stage2_results.json`.
