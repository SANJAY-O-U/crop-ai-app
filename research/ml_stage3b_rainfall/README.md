# ML Stage 3B — Two-stage rainfall model (Yelandur multi-GP)

**Evaluation against ERA5-Land reanalysis proxy — not observation.**

Reanalysis-to-reanalysis spatial transfer (ERA5 0.25° → ERA5-Land 0.1°),
rainfall only.

> The effective spatial sample comprises 4 ERA5-Land cell groups, so these
> results are exploratory and do not establish generalized Panchayat-level
> forecasting skill.

## Methods compared (same test rows)

| Method | Definition |
|---|---|
| `A_bilinear` | ERA5 0.25° rainfall bilinearly paired to the target cell; no training |
| `C4_hgb_regression` | Stage 2 Model C rainfall regression (same config and 13 features), refit here; must reproduce Stage 2 exactly |
| `S_two_stage` | occurrence classifier → amount regressor (below) |

### S_two_stage

1. **Wet definition (fixed in advance):** an hour is wet if rainfall
   > **0.1 mm**. ERA5-Land has many sub-0.1 mm drizzle hours (57 % of hours
   are > 0 mm, ~17 % exceed 0.1 mm).
2. **Occurrence:** `HistGradientBoostingClassifier` (log loss) on all
   training hours, label = target > 0.1 mm.
3. **Threshold (per fold, training rows only):** an inner temporal split of
   the fold's training period — inner-train 2021, 7-day gap
   (2022-01-01 – 2022-01-07), inner-val 2022-01-08 – 2022-12-24. A
   classifier fit on inner-train scores inner-val; the threshold on the grid
   0.05, 0.10, … 0.95 with the highest inner-val F1 is chosen (ties → lowest).
   The classifier is then refit on all training rows. 2023 is never used.
4. **Amount:** `HistGradientBoostingRegressor` with **Poisson** loss, trained
   only on wet training hours (log link → strictly positive amounts).
5. **Prediction:** amount if p(wet) ≥ threshold, else exactly 0.

Both models use Stage 2's fixed settings (`learning_rate=0.1`,
`max_iter=200`, `max_leaf_nodes=31`, `min_samples_leaf=200`,
`early_stopping=False`, `random_state=0`); only the loss differs. No
hyperparameter search. Features: Stage 2 Model C's 13 (5 same-timestamp
ERA5 coarse variables, 4 static GP context features, 4 cyclic UTC time
features). No ERA5-Land-derived, target-cell, GP-identity or fold columns.

## Folds and population

The exact Phase 2D folds: leave-one-ERA5-Land-cell-group-out, train
2021-01-01 – 2022-12-24 UTC, 7-day embargo, test 2023. Agara excluded,
Mamballi unavailable. Rainfall processing unchanged (11 missing first-hour
rows excluded; 5,001 clamped steps ≤ ~0.000034 mm).

## Metrics

Per fold, fold-mean and row-pooled, for raw predictions and — separately —
a **post-processing diagnostic** with `max(prediction, 0)`:

- overall MAE / RMSE / bias (prediction − target), invalid (negative) count;
- occurrence (value > 0.1 mm): TP/FP/FN/TN, precision, recall, F1, predicted
  and observed wet fractions; plus the classifier's own decision;
- amount on observed-wet hours and on hit hours (observed and predicted wet);
- dry-hour behaviour: MAE, mean prediction, share predicted exactly 0,
  share falsely predicted wet;
- totals: predicted vs observed total rainfall.

## Limitations

- Only 4 spatial groups; hourly rows are not independent.
- Wet threshold 0.1 mm is a fixed choice; results for occurrence depend on it.
- Threshold selection validates on 2022 within the same training cell
  groups (temporal, not spatial, inner validation).
- 2023 (test) was much drier than 2021–2022 (wet-hour share ~12 % vs ~19 %).
- Hard gating sets drizzle (≤ threshold) hours to exactly 0, which adds
  error on the many small non-zero ERA5-Land values.

## Run

```bash
python research/ml_stage3b_rainfall/evaluation.py
```

Writes `rainfall_results.json` (including SHA-256 of the Stage 1/2/3A
results and the Phase 2D manifest at run time). No model file is saved.
