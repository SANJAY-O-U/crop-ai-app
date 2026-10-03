# CropCastAI - offline daily evaluation bridge

**Evaluation against the ERA5-Land reanalysis proxy -- not observation.** The station diagnostic (section 8) is separate and is never pooled with it. Nothing here is deployed; no model is saved; the live API and the frontend are unchanged.

Run: 2026-10-03T19:02:22+00:00 - commit `6134a22d69` - dataset `data/training/yelandur_multi_gp.parquet` (sha256 `c25017849d5b47f4...`, 1,445,400 hourly rows) - runtime 853.4 s.

## Bottom line

Variables whose daily-grain candidates meet the pre-declared evidence rule against the ERA5-Land proxy (necessary, not sufficient, to build a deployable model):

- **Temperature (daily min)**: C_daily_hgb - MAE skill vs the constant-offset diagnostic +21.0%; station diagnostic of the hourly correction: positive (MAE skill +13.3%)

Variables that should **stay pass-through (block value / current behaviour) for now**: Temperature (daily max), Rainfall (daily total), Humidity (daily mean), Wind (daily max).

No statement here is a claim of accuracy: all numbers measure agreement with ERA5-Land from ERA5 reanalysis inputs, not with real Panchayat weather and not with an NWP forecast.

## Answers

**1. Does daily correction improve temperature?**

- Temperature (daily max):
  - C_daily_hgb: MAE skill +16.9% (positive; 95% CI +8.3% to +25.3%), RMSE skill +19.0% (positive), folds with MAE gain 2/4, quarters 3/4
  - R_daily_ridge: MAE skill -39.3% (negative; 95% CI -49.9% to -28.7%), RMSE skill -89.9% (negative), folds with MAE gain 2/4, quarters 0/4
  - C_hourly_agg: MAE skill +27.5% (positive; 95% CI +19.6% to +35.2%), RMSE skill +28.9% (positive), folds with MAE gain 2/4, quarters 4/4
- Temperature (daily min):
  - C_daily_hgb: MAE skill +35.1% (positive; 95% CI +27.4% to +42.1%), RMSE skill +32.5% (positive), folds with MAE gain 4/4, quarters 4/4
  - R_daily_ridge: MAE skill -13.9% (negative; 95% CI -24.0% to -4.0%), RMSE skill -66.4% (negative), folds with MAE gain 3/4, quarters 2/4
  - C_hourly_agg: MAE skill +46.2% (positive; 95% CI +39.7% to +52.2%), RMSE skill +44.2% (positive), folds with MAE gain 4/4, quarters 4/4

**2. Humidity?**

- Humidity (daily mean):
  - C_daily_hgb: MAE skill +12.4% (positive; 95% CI +0.5% to +22.5%), RMSE skill +11.9% (positive), folds with MAE gain 3/4, quarters 2/4
  - R_daily_ridge: MAE skill -52.8% (negative; 95% CI -72.5% to -36.3%), RMSE skill -95.2% (negative), folds with MAE gain 2/4, quarters 0/4
  - C_hourly_agg: MAE skill +27.0% (positive; 95% CI +15.6% to +37.3%), RMSE skill +26.1% (positive), folds with MAE gain 4/4, quarters 4/4

**3. Wind?**

- Wind (daily max):
  - C_daily_hgb: MAE skill +50.4% (positive; 95% CI +45.0% to +55.8%), RMSE skill +43.3% (positive), folds with MAE gain 4/4, quarters 4/4
  - R_daily_ridge: MAE skill +41.9% (positive; 95% CI +34.0% to +48.7%), RMSE skill +28.0% (positive), folds with MAE gain 3/4, quarters 4/4
  - C_hourly_agg: MAE skill +55.2% (positive; 95% CI +49.1% to +60.8%), RMSE skill +47.8% (positive), folds with MAE gain 4/4, quarters 4/4

**4. Rainfall?**

- Rainfall (daily total):
  - C_daily_hgb: MAE skill -60.5% (negative; 95% CI -124.1% to -19.2%), RMSE skill -182.0% (negative), folds with MAE gain 0/4, quarters 1/4
  - R_daily_ridge: MAE skill -20.7% (negative; 95% CI -36.5% to -10.7%), RMSE skill -2.4% (negative), folds with MAE gain 1/4, quarters 0/4
  - C_hourly_agg: MAE skill -4.9% (negative; 95% CI -35.4% to +15.3%), RMSE skill -70.5% (negative), folds with MAE gain 2/4, quarters 3/4

**5. Does it outperform block-as-is?** See the skill lines above: a candidate outperforms block-as-is only where its MAE and RMSE skill are both labelled positive with a bootstrap interval above zero.

**6. Does it outperform the current production baseline?**

- Temperature (daily max): production baseline vs block: MAE skill +5.5% (positive); constant-offset diagnostic vs block: MAE skill -10.8%; C_daily_hgb vs production: MAE skill +12.0%; R_daily_ridge vs production: MAE skill -47.4%; C_hourly_agg vs production: MAE skill +23.2%
- Temperature (daily min): production baseline vs block: MAE skill -10.7% (negative); constant-offset diagnostic vs block: MAE skill +17.9%; C_daily_hgb vs production: MAE skill +41.4%; R_daily_ridge vs production: MAE skill -2.9%; C_hourly_agg vs production: MAE skill +51.4%
- Rainfall (daily total): production baseline vs block: MAE skill -0.7% (zero); constant-offset diagnostic vs block: MAE skill -0.9%; C_daily_hgb vs production: MAE skill -59.3%; R_daily_ridge vs production: MAE skill -19.8%; C_hourly_agg vs production: MAE skill -4.1%
- Humidity (daily mean): production baseline vs block: MAE skill -8.4% (negative); constant-offset diagnostic vs block: MAE skill -1.6%; C_daily_hgb vs production: MAE skill +19.1%; R_daily_ridge vs production: MAE skill -41.0%; C_hourly_agg vs production: MAE skill +32.6%
- Wind (daily max): production baseline vs block: MAE skill -1.4% (negative); constant-offset diagnostic vs block: MAE skill +38.5%; C_daily_hgb vs production: MAE skill +51.1%; R_daily_ridge vs production: MAE skill +42.7%; C_hourly_agg vs production: MAE skill +55.8%

**7. Stability across spatial and temporal splits** - folds = the 4 held-out cell groups; quarters = Q1-Q4 of the 2023 test year. Counts of folds/quarters with a MAE gain are in the skill lines and tables below.

**8. Real observations** - see section 8.

**9/10. Which variables proceed / stay pass-through** - see Bottom line. Rule (pre-declared in `config.py`): pooled_mae_skill_vs_block_gt = 0.01; pooled_rmse_skill_vs_block_gt = 0.01; min_folds_mae_positive_of_4 = 3; min_quarters_mae_positive_of_4 = 3; bootstrap_ci_lower_mae_skill_gt = 0.0; must_beat_production_baseline_mae = True; rainfall_default = pass_through.

## 1. Pooled results by variable (10 GPs, 2023 test days)

### Temperature (daily max) (degC) - n = 3,640 GP-days

| method | MAE | RMSE | bias | MAE skill vs block | RMSE skill vs block | folds MAE gain | quarters MAE gain |
|---|---|---|---|---|---|---|---|
| block_as_is | 0.912 | 1.182 | 0.556 | reference | reference | - | - |
| production_baseline | 0.861 | 1.067 | 0.556 | +5.5% (positive) | +9.7% (positive) | 2/4 | 3/4 |
| block_plus_train_bias | 1.011 | 1.212 | -0.369 | -10.8% (negative) | -2.6% (negative) | 2/4 | 2/4 |
| C_daily_hgb | 0.758 | 0.958 | -0.142 | +16.9% (positive) | +19.0% (positive) | 2/4 | 3/4 |
| R_daily_ridge | 1.270 | 2.244 | -0.817 | -39.3% (negative) | -89.9% (negative) | 2/4 | 0/4 |
| C_hourly_agg | 0.662 | 0.840 | -0.173 | +27.5% (positive) | +28.9% (positive) | 2/4 | 4/4 |

Per fold MAE (held-out cell group) - 1: block_as_is=1.218, production_baseline=1.102, C_daily_hgb=0.801; 2: block_as_is=2.182, production_baseline=0.817, C_daily_hgb=0.805; 3: block_as_is=0.659, production_baseline=0.859, C_daily_hgb=0.710; 4: block_as_is=0.622, production_baseline=0.719, C_daily_hgb=0.778

Per quarter MAE - Q1: block_as_is=0.709, production_baseline=0.522, C_daily_hgb=0.603; Q2: block_as_is=0.851, production_baseline=0.794, C_daily_hgb=0.899; Q3: block_as_is=0.999, production_baseline=1.054, C_daily_hgb=0.792; Q4: block_as_is=1.081, production_baseline=1.064, C_daily_hgb=0.735

Decision per candidate: C_daily_hgb: KEEP_PASS_THROUGH; R_daily_ridge: KEEP_PASS_THROUGH; C_hourly_agg: KEEP_PASS_THROUGH

### Temperature (daily min) (degC) - n = 3,640 GP-days

| method | MAE | RMSE | bias | MAE skill vs block | RMSE skill vs block | folds MAE gain | quarters MAE gain |
|---|---|---|---|---|---|---|---|
| block_as_is | 0.971 | 1.229 | 0.903 | reference | reference | - | - |
| production_baseline | 1.075 | 1.254 | 0.903 | -10.7% (negative) | -2.0% (negative) | 2/4 | 0/4 |
| block_plus_train_bias | 0.798 | 0.950 | -0.163 | +17.9% (positive) | +22.8% (positive) | 2/4 | 2/4 |
| C_daily_hgb | 0.630 | 0.830 | 0.184 | +35.1% (positive) | +32.5% (positive) | 4/4 | 4/4 |
| R_daily_ridge | 1.106 | 2.045 | -0.677 | -13.9% (negative) | -66.4% (negative) | 3/4 | 2/4 |
| C_hourly_agg | 0.522 | 0.686 | 0.070 | +46.2% (positive) | +44.2% (positive) | 4/4 | 4/4 |

Per fold MAE (held-out cell group) - 1: block_as_is=1.506, production_baseline=1.366, C_daily_hgb=0.864; 2: block_as_is=2.042, production_baseline=0.835, C_daily_hgb=0.643; 3: block_as_is=0.666, production_baseline=1.088, C_daily_hgb=0.575; 4: block_as_is=0.665, production_baseline=0.944, C_daily_hgb=0.542

Per quarter MAE - Q1: block_as_is=1.315, production_baseline=1.399, C_daily_hgb=0.938; Q2: block_as_is=0.769, production_baseline=0.818, C_daily_hgb=0.611; Q3: block_as_is=0.680, production_baseline=0.850, C_daily_hgb=0.416; Q4: block_as_is=1.130, production_baseline=1.242, C_daily_hgb=0.565

Decision per candidate: C_daily_hgb: CANDIDATE_MEETS_PROPOSED_EVIDENCE_RULE; R_daily_ridge: KEEP_PASS_THROUGH; C_hourly_agg: CANDIDATE_MEETS_PROPOSED_EVIDENCE_RULE

### Rainfall (daily total) (mm) - n = 3,640 GP-days

| method | MAE | RMSE | bias | MAE skill vs block | RMSE skill vs block | folds MAE gain | quarters MAE gain |
|---|---|---|---|---|---|---|---|
| block_as_is | 0.271 | 0.653 | 0.121 | reference | reference | - | - |
| production_baseline | 0.273 | 0.658 | 0.121 | -0.7% (zero) | -0.8% (zero) | 1/4 | 2/4 |
| block_plus_train_bias | 0.274 | 0.643 | 0.043 | -0.9% (zero) | +1.5% (positive) | 2/4 | 1/4 |
| C_daily_hgb | 0.435 | 1.841 | -0.049 | -60.5% (negative) | -182.0% (negative) | 0/4 | 1/4 |
| R_daily_ridge | 0.327 | 0.668 | 0.056 | -20.7% (negative) | -2.4% (negative) | 1/4 | 0/4 |
| C_hourly_agg | 0.284 | 1.113 | -0.064 | -4.9% (negative) | -70.5% (negative) | 2/4 | 3/4 |

Per fold MAE (held-out cell group) - 1: block_as_is=0.342, production_baseline=0.347, C_daily_hgb=0.499; 2: block_as_is=0.345, production_baseline=0.414, C_daily_hgb=0.547; 3: block_as_is=0.204, production_baseline=0.207, C_daily_hgb=0.400; 4: block_as_is=0.289, production_baseline=0.265, C_daily_hgb=0.402

Per quarter MAE - Q1: block_as_is=0.060, production_baseline=0.057, C_daily_hgb=0.058; Q2: block_as_is=0.428, production_baseline=0.434, C_daily_hgb=0.805; Q3: block_as_is=0.341, production_baseline=0.364, C_daily_hgb=0.487; Q4: block_as_is=0.250, production_baseline=0.232, C_daily_hgb=0.383

Decision per candidate: C_daily_hgb: KEEP_PASS_THROUGH; R_daily_ridge: KEEP_PASS_THROUGH; C_hourly_agg: KEEP_PASS_THROUGH

### Humidity (daily mean) (%) - n = 3,640 GP-days

| method | MAE | RMSE | bias | MAE skill vs block | RMSE skill vs block | folds MAE gain | quarters MAE gain |
|---|---|---|---|---|---|---|---|
| block_as_is | 2.391 | 2.999 | 0.874 | reference | reference | - | - |
| production_baseline | 2.591 | 3.245 | 0.874 | -8.4% (negative) | -8.2% (negative) | 0/4 | 0/4 |
| block_plus_train_bias | 2.428 | 3.018 | 0.441 | -1.6% (negative) | -0.6% (zero) | 2/4 | 1/4 |
| C_daily_hgb | 2.095 | 2.641 | -0.183 | +12.4% (positive) | +11.9% (positive) | 3/4 | 2/4 |
| R_daily_ridge | 3.653 | 5.853 | 1.024 | -52.8% (negative) | -95.2% (negative) | 2/4 | 0/4 |
| C_hourly_agg | 1.745 | 2.217 | 0.480 | +27.0% (positive) | +26.1% (positive) | 4/4 | 4/4 |

Per fold MAE (held-out cell group) - 1: block_as_is=1.959, production_baseline=1.987, C_daily_hgb=2.571; 2: block_as_is=2.340, production_baseline=3.304, C_daily_hgb=1.907; 3: block_as_is=2.306, production_baseline=2.423, C_daily_hgb=1.696; 4: block_as_is=2.808, production_baseline=2.979, C_daily_hgb=2.373

Per quarter MAE - Q1: block_as_is=3.332, production_baseline=3.510, C_daily_hgb=2.206; Q2: block_as_is=2.500, production_baseline=2.690, C_daily_hgb=2.219; Q3: block_as_is=1.692, production_baseline=1.875, C_daily_hgb=1.907; Q4: block_as_is=2.070, production_baseline=2.318, C_daily_hgb=2.053

Decision per candidate: C_daily_hgb: KEEP_PASS_THROUGH; R_daily_ridge: KEEP_PASS_THROUGH; C_hourly_agg: CANDIDATE_MEETS_PROPOSED_EVIDENCE_RULE

### Wind (daily max) (km/h) - n = 3,640 GP-days

| method | MAE | RMSE | bias | MAE skill vs block | RMSE skill vs block | folds MAE gain | quarters MAE gain |
|---|---|---|---|---|---|---|---|
| block_as_is | 1.587 | 1.906 | 1.450 | reference | reference | - | - |
| production_baseline | 1.608 | 2.029 | 1.449 | -1.4% (negative) | -6.4% (negative) | 2/4 | 0/4 |
| block_plus_train_bias | 0.976 | 1.289 | 0.042 | +38.5% (positive) | +32.4% (positive) | 4/4 | 4/4 |
| C_daily_hgb | 0.787 | 1.081 | -0.014 | +50.4% (positive) | +43.3% (positive) | 4/4 | 4/4 |
| R_daily_ridge | 0.922 | 1.373 | -0.440 | +41.9% (positive) | +28.0% (positive) | 3/4 | 4/4 |
| C_hourly_agg | 0.710 | 0.995 | -0.203 | +55.2% (positive) | +47.8% (positive) | 4/4 | 4/4 |

Per fold MAE (held-out cell group) - 1: block_as_is=1.946, production_baseline=2.001, C_daily_hgb=0.800; 2: block_as_is=2.367, production_baseline=3.508, C_daily_hgb=0.802; 3: block_as_is=1.275, production_baseline=1.108, C_daily_hgb=0.813; 4: block_as_is=1.503, production_baseline=1.381, C_daily_hgb=0.739

Per quarter MAE - Q1: block_as_is=1.404, production_baseline=1.412, C_daily_hgb=0.612; Q2: block_as_is=1.479, production_baseline=1.517, C_daily_hgb=0.854; Q3: block_as_is=2.193, production_baseline=2.208, C_daily_hgb=0.971; Q4: block_as_is=1.265, production_baseline=1.289, C_daily_hgb=0.706

Decision per candidate: C_daily_hgb: CANDIDATE_MEETS_PROPOSED_EVIDENCE_RULE; R_daily_ridge: CANDIDATE_MEETS_PROPOSED_EVIDENCE_RULE; C_hourly_agg: CANDIDATE_MEETS_PROPOSED_EVIDENCE_RULE

## 2. Hourly -> daily aggregation (input -> aggregation -> output -> units)

| hourly input | aggregation | daily output | unit | mirrors Open-Meteo field |
|---|---|---|---|---|
| temperature_c | max over the 24 hourly values of the IST day | temperature_max_c | degC | temperature_2m_max |
| temperature_c | min over the 24 hourly values of the IST day | temperature_min_c | degC | temperature_2m_min |
| rainfall_mm | sum over the 24 hourly values of the IST day | rainfall_mm | mm | precipitation_sum |
| relative_humidity_pct | mean over the 24 hourly values of the IST day | humidity_pct | % | relative_humidity_2m_mean |
| wind_speed_kmph | max over the 24 hourly values of the IST day | wind_kmph | km/h | windspeed_10m_max |

IST local calendar day (Phase 2D local_date_ist, UTC+05:30, as Open-Meteo timezone=auto for Karnataka). A daily value requires all 24 hourly values; the 2021-01-01 IST day is incomplete and drops out.

## 3. Baselines and candidates

- **block_as_is**: block daily value unchanged
- **production_baseline**: backend/app/downscaling/baseline.py::apply_baseline (imported) on the block daily values with the GP-vs-block elevation difference
- **block_plus_train_bias**: DIAGNOSTIC (not a candidate): block value + one constant, the mean (target - block) over the fold's train days; shows how much of any gain is plain bias removal. Not part of the pre-declared evidence rule.
- **C_daily_hgb**: Stage 2 HGB config on daily production-grain features
- **R_daily_ridge**: Stage 1 ridge definition on the same daily features
- **C_hourly_agg**: Stage 3A C4 hourly model, predictions clipped to physical bounds then aggregated to daily (needs hourly inputs the live API lacks: reference only)

Block input: Per timestamp, the mean over the 10 primary Yelandur GPs of the ERA5 0.25 deg bilinear value (the same value for every Panchayat, like a block forecast), then aggregated to daily. Block elevation = mean of the 10 GP mean elevations. A dataset-derived proxy for a block forecast: reanalysis, not an NWP forecast.

Daily features: block_temperature_max_c, block_temperature_min_c, block_rainfall_mm, block_humidity_pct, block_wind_kmph, elevation_mean_m, elevation_range_m, elevation_delta_m, sin_day_of_year, cos_day_of_year. HGB config: `{'loss': 'squared_error', 'learning_rate': 0.1, 'max_iter': 200, 'max_leaf_nodes': 31, 'max_depth': None, 'min_samples_leaf': 200, 'l2_regularization': 0.0, 'max_bins': 255, 'early_stopping': False, 'random_state': 0}`; ridge alpha 1.0.

## 4. Splits

- **source**: Phase 2D hourly fold labels (unchanged), converted to daily: a GP-day is train/test only if all 24 hourly rows agree
- **spatial**: leave-one-ERA5-Land-cell-group-out, 4 folds; each of the 10 primary GPs is test in exactly one fold
- **temporal**: train 2021-01-01..2022-12-24, 7-day embargo, test 2023 (UTC); mixed/embargo days unused
- **validation**: no separate validation period: configurations were fixed a priori (no tuning), so no validation split is needed

Per fold audit:

- split_fold_1: held-out `E5L_12.00N_77.10E`; train days 2021-01-02..2022-12-24; test days 2023-01-02..2023-12-31; gap 9 d; train GP-days 5,776; test GP-days 728; cell groups disjoint: True
- split_fold_2: held-out `E5L_12.00N_77.20E`; train days 2021-01-02..2022-12-24; test days 2023-01-02..2023-12-31; gap 9 d; train GP-days 6,498; test GP-days 364; cell groups disjoint: True
- split_fold_3: held-out `E5L_12.10N_77.00E`; train days 2021-01-02..2022-12-24; test days 2023-01-02..2023-12-31; gap 9 d; train GP-days 4,332; test GP-days 1,456; cell groups disjoint: True
- split_fold_4: held-out `E5L_12.10N_77.10E`; train days 2021-01-02..2022-12-24; test days 2023-01-02..2023-12-31; gap 9 d; train GP-days 5,054; test GP-days 1,092; cell groups disjoint: True

Skill: skill = 1 - candidate_error / block_as_is_error, for MAE and RMSE; abs_bias uses |bias|. >+0.01 positive, <-0.01 negative, else zero (numbers always reported).

## 8. Station-observation diagnostic (independent of the ERA5-Land proxy)

Station-observation diagnostic. Not Panchayat ground truth; model = frozen Stage 4D hourly C4 aggregated to daily over the matched hours. Compared against A1 (coarse ERA5 value, the block-as-is analogue). Station-days need at least 6 matched hours. Rainfall is not evaluated: Stage 5 found no usable wet observation periods (outcome INSUFFICIENT).

| daily variable | station-days | A1 (coarse) MAE | C4 hourly-agg MAE | ERA5-Land target MAE | C4 MAE skill vs A1 | 95% CI | label |
|---|---|---|---|---|---|---|---|
| Humidity (daily mean) | 496 | 5.956 | 6.058 | 6.531 | -1.7% | -6.9% to +3.4% | negative |
| Temperature (daily max) | 497 | 1.403 | 1.187 | 1.077 | +15.4% | +3.7% to +25.6% | positive |
| Temperature (daily min) | 497 | 0.736 | 0.637 | 0.862 | +13.3% | +0.9% to +23.4% | positive |
| Wind (daily max) | 497 | 5.390 | 6.099 | 5.689 | -13.2% | -15.8% to -10.6% | negative |

Per station (C4 MAE skill vs A1): Humidity (daily mean) - central_plateau: -8.3% (n=132), coastal_inland_coast: +4.8% (n=364); Temperature (daily max) - central_plateau: +42.8% (n=133), coastal_inland_coast: +6.7% (n=364); Temperature (daily min) - central_plateau: +23.9% (n=133), coastal_inland_coast: +5.0% (n=364); Wind (daily max) - central_plateau: +9.6% (n=133), coastal_inland_coast: -18.7% (n=364)

## Limitations

- Target is ERA5-Land reanalysis (a model), not observation; input is ERA5 reanalysis, not an NWP forecast.
- Only 4 independent spatial cell groups (10 GPs); one test year (2023, a dry year); rows within a day/cell are strongly dependent.
- The block input is derived from the same 10 GPs' coarse values; with 4 cell groups the elevation signal cannot be learned robustly.
- C_hourly_agg needs hourly inputs unavailable from the daily API; it is an upper-bound reference only.
- Observation diagnostic: stations are 6-17 km from Panchayat centroids, only the Stage 4D hourly model is checked there, and rainfall is not evaluable.
- No model is saved or deployed; no production claim follows from this evaluation.
