# ML Stage 3A — Feature-group ablation of Model C

**Evaluation against ERA5-Land reanalysis proxy — not observation.**

Reanalysis-to-reanalysis spatial transfer (ERA5 0.25° → ERA5-Land 0.1°).

> The effective spatial sample comprises 4 ERA5-Land cell groups, so these
> results are exploratory and do not establish generalized Panchayat-level
> forecasting skill.

## What changes, what does not

Only the feature list changes. Everything else is Stage 2, imported rather
than copied: the fixed `HistGradientBoostingRegressor` configuration
(`ml_stage2.model.CONFIG`, no tuning), feature construction
(`ml_stage2.features`), the Phase 2D folds, the leakage audit, and the
invalid-prediction definitions. Rainfall processing is unchanged, and the
HGB rainfall results are a diagnostic only.

| Variant | Features |
|---|---|
| C1_coarse_weather | 5 same-timestamp ERA5 coarse variables |
| C2_plus_elevation | C1 + `elevation_mean_m`, `elevation_range_m` |
| C3_plus_spatial | C2 + `centroid_to_cell_km`, `intersecting_cell_count` |
| C4_plus_time_full_C | C3 + `sin_hour`, `cos_hour`, `sin_day_of_year`, `cos_day_of_year` (= Stage 2 Model C) |

`A_bilinear` (the direct ERA5 bilinear value) is scored on the same rows as
a no-training reference. C4 is checked to reproduce Stage 2's Model C
metrics exactly; the run stops if it does not.

## Reported

Per fold × variable × variant: MAE, RMSE, bias (prediction − target),
invalid predictions. Aggregates: fold-mean ± std and row-pooled.
Incremental deltas (later variant − earlier variant) for each added
feature group, with the number of folds where MAE went down or up. No
variant is ranked.

## Run

```bash
python research/ml_stage3_ablation/evaluation.py
```

Writes `ablation_results.json`. No model file is written.
