# Stage 4D — cross-area spatial generalization (research only)

**Performance against the ERA5-Land reanalysis proxy — not observation.**
ERA5 0.25° is the coarse predictor; ERA5-Land 0.1° nearest-cell values are
the target proxy. Nothing here is observational validation, and nothing is
imported by, or ready for, the live CropCastAI application.

## Inputs (frozen, read-only)

- Stage 4C dataset: 11 Parquet files, 36,397,800 rows, 277 Panchayats,
  110 ERA5-Land cells, 2021-01-01 00:00 – 2023-12-31 23:00 UTC. Each file's
  SHA-256 and row count are verified against `stage4_dataset_manifest.json`
  before loading (`data4d.verify_dataset_identity`).
- Folds: `stage4_acquisition_manifest.json` → `fold_design` (frozen Stage
  4A/4B). The per-row fold columns in the data are checked against it.
- Yelandur reference: the Phase 2D dataset, COMPLETE GPs only, 2023. It is
  never trained on; every area-fold model is also scored on it.

## Karwar exception

The frozen selection required ≥ 6 ERA5-Land cells. The Stage 4C land/sea
audit found `E5L_14.90N_74.10E` is sea, so Majali (220655) and Mudgeri
(220657) were excluded as `NON_LAND_TARGET_CELL`, with no substitution.
Karwar is evaluated with 14 Panchayats and 5 cells, **below** the original
criterion. Every output flags it (`karwar_exception`,
`includes_karwar_exception`).

## Splits (no random rows, no shuffling across geography)

Every fold trains on the training geography × 2021-01-01–2022-12-24 and
tests on the held-out geography × 2023 (7-day embargo between).

| Scheme | Folds | Held out |
|---|---|---|
| area (primary) | 11 | one Taluka Panchayat |
| district | = area | one area per district (frozen design); verified, not re-computed |
| region | 6 | one geographic regime |
| cellblock (diagnostic only) | 5 | 3×3-cell blocks, frozen 1-cell buffer dropped from training |

## Models (frozen configurations, no tuning)

| Method | Definition |
|---|---|
| A1_bilinear | ERA5 bilinear value of the target variable |
| A2_nearest | ERA5 nearest-point value |
| B_ridge | Stage 1 ridge (α = 1.0, standardization fit on training rows) |
| C1–C4 | Stage 2 `HistGradientBoostingRegressor` (`ml_stage2.model.CONFIG`, random_state 0) on the Stage 3A feature lists |

Each fold's feature matrix is audited against a forbidden-column list
(targets, nearest values, GP/area/cell identity, fold columns, timestamps)
before fitting, and NaN features are refused. Rainfall uses the same
models, and the Stage 3B wet-hour metrics are reported. The Stage 3B
two-stage model is not re-used.

## Run

```bash
python research/stage4d_ml/evaluate4d.py --scheme area
python research/stage4d_ml/evaluate4d.py --scheme region
python research/stage4d_ml/evaluate4d.py --scheme cellblock
python research/stage4d_ml/evaluate4d.py --determinism-check
python research/stage4d_ml/evaluate4d.py --assemble
```

Outputs: `results/<scheme>/<fold>.json` (per-fold metrics, per-Panchayat and
per-cell metrics, isolation audit, prediction SHA-256),
`results/tables/*.csv`, `models/model_configuration.json` (no fitted model
objects are saved), and `stage4d_results.json`.

## Limitations

11 areas in 6 regions, one 3-year window, and a single test year (2023).
Neighbouring cells remain correlated even ≥ 3 cells apart. Correlations
across 11 areas are exploratory. Performance is measured against a
reanalysis, not against observations.
