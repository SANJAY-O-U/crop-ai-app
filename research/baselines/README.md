# ML Stage 1 — Baselines (Yelandur multi-GP)

**Evaluation against ERA5-Land reanalysis proxy — not observation.**

This experiment measures reanalysis-to-reanalysis spatial transfer:
ERA5 0.25° (coarse input) → ERA5-Land 0.1° nearest cell (target proxy).

> The effective spatial sample comprises 4 ERA5-Land cell groups, so these
> results are exploratory and do not establish generalized Panchayat-level
> forecasting skill.

The dataset's 1,445,400 rows are **not** independent samples: GPs in the
same cell group share identical target series, hours are autocorrelated,
and neighbouring cells are highly correlated.

## Methods

| Method | Prediction | Training |
|---|---|---|
| **A_bilinear** (Baseline A) | `coarse_bilinear_value` | none |
| **A_nearest** (transparency) | `coarse_nearest_value` | none |
| **B_ridge** (Baseline B) | ridge regression on the 5 features below | per fold × variable, training rows only |

Baseline B features: `coarse_bilinear_value`, `elevation_mean_m`,
`elevation_range_m`, `centroid_to_cell_km`, `intersecting_cell_count`.
Features are standardized with training-row means/stds only; the intercept
is the training-row target mean; `alpha = 1.0` is fixed a priori (no
hyperparameter search). Never used as inputs: the target, the area-weighted
diagnostic, target-cell coordinates, `cell_group_id`, GP identity, fold
columns, or any other target-derived field (`baseline.FORBIDDEN_FEATURES`).

No clipping or post-processing is applied to predictions; physically
out-of-range Baseline B predictions (negative rainfall/wind, RH outside
0–100 %) are counted in the results, not hidden.

## Splits

The existing Phase 2D folds, unchanged: leave-one-ERA5-Land-cell-group-out
(4 folds), training 2021-01-01 – 2022-12-24 UTC, 7-day embargo, test 2023.
Agara (PARTIAL) is excluded from every fold; Mamballi (UNAVAILABLE) has no
rows. The evaluator re-audits every fold and stops on any violation.

## Metrics

`mae`, `rmse`, `bias = mean(prediction − target)`, and `n` test records,
per fold × variable × method. Aggregates: unweighted mean ± sample std over
the 4 folds (each cell group counts once) and row-pooled metrics (weighted
by rows, so cell groups with more GPs count more).

## Rainfall

Phase 2D rainfall processing is unchanged. The 11 first-hour rows with no
de-accumulated value are excluded from every fold. 5,001 target rows carry
a clamped tiny negative step (max |step| ≈ 0.000034 mm, a float32 rounding
artifact documented in the Phase 2D manifest).

## Run

```bash
python research/baselines/evaluation.py
```

Writes `baseline_results.json` (metrics, per-fold coefficients, leakage
audits). No model file is saved.
