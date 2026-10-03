# Phase 2D — Yelandur multi-GP spatial-transfer dataset

A **reanalysis-to-reanalysis spatial-transfer** dataset for the Yelandur
Gram Panchayats (GPs). No model is trained here.

| Role | Product | CDS dataset | Resolution |
|---|---|---|---|
| Coarse input | ERA5 reanalysis | `reanalysis-era5-single-levels` (`product_type: reanalysis`) | 0.25° |
| Target proxy | ERA5-Land reanalysis | `reanalysis-era5-land` | 0.1° |

Neither side is an observation, and neither is a forecast. Every row carries
`source_note = "reanalysis proxy — not observation"`.

## Files

| File | Tracked? |
|---|---|
| `acquire.py` — multi-year monthly acquisition (isolated from the Phase 2A pilot) | yes |
| `pairing.py` — coarse→target-cell pairing, GP area weights | yes |
| `splits.py` — leakage-safe spatial/temporal fold assignment | yes |
| `build.py` — dataset + manifest builder | yes |
| `yelandur_multi_gp_manifest.json` — definitions, coverage, folds, provenance | yes |
| `data/training/yelandur_multi_gp.parquet` — the dataset | no (gitignored) |
| `data/raw/era5_land/multi_gp/`, `data/raw/era5/multi_gp/` — monthly raw files | no (gitignored) |

```bash
python research/multi_gp/acquire.py   # real CDS requests; skips months already on disk
python research/multi_gp/build.py
```

## Acquisition

- Window: **2021-01-01T00Z – 2023-12-31T23Z** (3 full years, 26,280 hours),
  one request per product per month (72 requests, cached per month).
- Auth: the existing `config.get_cds_client()` only. ZIP responses: the
  existing `era5_land.archive.ensure_netcdf()`.
- `era5_land/acquire.py` (the 72-hour pilot) is imported for its dataset and
  variable constants and is **not modified**; pilot files are not touched.
- ERA5-Land area = the Phase 2C linkage area `[12.25, 76.90, 11.85, 77.30]`
  (4×5 cells, identical to the linkage grid — checked at build time).
- ERA5 area = `[12.5, 76.75, 11.75, 77.5]` (4×4 native 0.25° points).

Verified from real CDS responses: ERA5 NetCDF arrives as a ZIP with an
`instant` member (t2m, d2m, u10, v10) and an `accum` member (tp), merged back
on load; ERA5 `tp` is already the hourly accumulation ending at `valid_time`;
ERA5-Land `tp` accumulates from 00 UTC and is de-accumulated with the
existing `pipeline.units` rule over the whole continuous window (so only the
very first hour, 2021-01-01T00Z, has no rainfall value). Units: K → °C,
m → mm, m s⁻¹ → km/h via `pipeline.units`; RH derived from T and Td.

## Pairing

- **Target**: ERA5-Land value of the cell nearest each GP centroid (from the
  Phase 2C linkage). GPs sharing that cell form a **cell group** and share an
  identical target series.
- **Secondary diagnostic** (`area_weighted_value`): area-weighted mean over
  the ERA5-Land cells the GP geometry intersects. Not a target.
- **Coarse**, per target cell, ERA5 values only:
  `coarse_bilinear_value` from the 4 enclosing ERA5 points, and
  `coarse_nearest_value` from the nearest ERA5 point. Three of the four
  primary cell groups share the same nearest ERA5 point (12.0N, 77.0E), so
  the nearest-point field alone cannot tell them apart.

## Splits

- Spatial: leave-one-cell-group-out over the 10 COMPLETE GPs → **4 folds**.
  The effective spatial sample size is **4 cell groups, not 10 GPs**.
- Temporal (every fold): train 2021-01-01 – 2022-12-24, 7-day embargo,
  test 2023 (UTC). No hourly row is ever randomly assigned.
- Agara (PARTIAL) is flagged and `excluded` in every fold. Mamballi
  (UNAVAILABLE) has zero rows.

See the manifest's `known_limitations` for what this dataset cannot support.
