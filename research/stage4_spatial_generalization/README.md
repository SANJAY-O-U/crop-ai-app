# Stage 4 — Spatial generalization: FEASIBILITY AUDIT ONLY

Offline, read-only audit of which Karnataka regions could add genuinely
independent ERA5-Land spatial groups to the frozen Yelandur experiment. No
data is downloaded, no dataset is built, no model is trained. The target
remains the ERA5-Land reanalysis proxy — not observation; nothing here is
observational validation.

The Yelandur 4-cell experiment and Stage 1/2/3A/3B artifacts are read-only
inputs.

## Candidate unit

Every LGD **Taluka Panchayat** in Karnataka (237; Yelandur, code 6132, is
the same tier) — audited statewide rather than hand-picked.

## Method (per GP, then per Taluka Panchayat)

| Step | Source | Rule |
|---|---|---|
| Identity | LGD `pri_local_bodies` | GP → Taluka Panchayat → Zila Panchayat; the run stops if any GP breaks the chain |
| Villages | LGD `villages_by_blocks`, `villages` | village → GP; village → Census-2001 code |
| Spatial proxy | DataMeet `ka.geojson` (1991 vintage) | **exact code only**: Census-2001 code zero-padded to 8 == `V_CT_CODE`; no name fallback, no fuzzy matching |
| Status | — | COMPLETE (all villages matched) / PARTIAL / UNAVAILABLE / NO_LGD_VILLAGES / INVALID_GEOMETRY (never repaired) |
| Centroid | — | Yelandur method: union of village polygons, centroid in EPSG:32643 |
| ERA5-Land cell | `grid.py` | nearest 0.1° centre (multiples of 0.1°, verified on real files) |
| ERA5 box | `grid.py` | enclosing 0.25° box (Phase 2D bilinear pairing) |
| Cell group | — | distinct nearest ERA5-Land cell among COMPLETE GPs (Phase 2D definition) |
| Elevation | GLO-30 `tileList.txt` + local tiles | tile availability for every candidate; zonal stats only where tiles are already on disk (N11–N12 × E076–E077) |

The method is validated by reproducing the frozen Yelandur artifacts
exactly: 12/12 GP statuses, 10/10 nearest cells, centroid difference 0.0°,
4 cells. The run stops otherwise.

## Pre-specified criteria (`criteria.py`, fixed before the run)

- **RECOMMEND_FOR_SHORTLIST:** ≥ 80 % of LGD GPs COMPLETE, ≥ 3 ERA5-Land
  cells not used by Yelandur, and a centroid ≥ 50 km from Yelandur's.
- **CONDITIONAL:** passes those, but a new cell centre falls outside every
  Karnataka village polygon (possible sea / other-state cell; ERA5-Land
  land-sea mask not checked offline), or a COMPLETE GP contains a village
  LGD maps to more than one GP.
- **EXCLUDE:** fails any RECOMMEND criterion (reasons recorded).

## Outputs

- `feasibility_audit.json`: statewide counts, provenance (SHA-256 of every
  source), the Yelandur reproduction check, per-district summary, and the
  full per-candidate audit (items 1–8).
- `taluka_panchayat_audit.csv`: one row per candidate.

```bash
python research/stage4_spatial_generalization/audit.py
```

## Stage 4A/4B — land/sea status, selection, fold design (`design.py`)

```bash
python research/stage4_spatial_generalization/design.py   # writes stage4_acquisition_manifest.json
```

**4A land/sea.** Not resolvable offline: every local ERA5-Land file is
inland with no missing values, and no mask or coastline dataset is on disk.
The 31 CONDITIONAL candidates stay `UNRESOLVED_PENDING_MASK` and are not
eligible. The manifest records the exact single-hour ERA5-Land request
(`land_sea.mask_request`; rule: a cell is land iff its value is not
missing). It must also gate every selected cell before acquisition. The
shared-village flag (Basavakalyan, Bhatkal) is re-checked offline by
dropping the affected GPs.

**4B selection (`selection.py`, deterministic).** Pool =
RECOMMEND_FOR_SHORTLIST only. Two rounds over 6 regimes (`regimes.py`, a
project-authored conventional grouping, not an official zonation). Each
pick needs ≥ 6 cells, a Zila Panchayat not already represented, and ≥ 3
cells (Chebyshev) from every cell of Yelandur and of already-selected
areas. Among those it maximizes the minimum distance to already-chosen
centroids (maximin spread), so it does not simply pick the largest areas.

**Folds (`folds.py`), designed before acquisition.** Phase 2D temporal split
in every fold, no random hourly splits. `taluka_holdout` (primary);
`district_holdout` (identical, one area per district); `regional_holdout`
(leave-one-regime-out); `cell_group_diagnostic` (3×3-cell blocks, 5 folds,
1-cell buffer dropped from training; diagnostic only). Yelandur is never
trained on and serves as an extra reference region.

## Stage 4C — acquisition and expanded dataset (`acquire4c.py`, `build4c.py`)

```bash
python research/stage4_spatial_generalization/acquire4c.py probe|tiles|weather
python research/stage4_spatial_generalization/build4c.py
```

- **Land/sea validation:** the single-hour ERA5-Land request from the
  frozen design manifest. Of the 111 expected cells, 110 are land;
  `E5L_14.90N_74.10E` (Karwar) is not. Its 2 GPs (Majali, Mudgeri) are
  excluded as `NON_LAND_TARGET_CELL` and never re-assigned. This is the only
  documented correction.
- **Weather:** 72 requests, one combined area per product per month (the
  union of the frozen per-area boxes). Every file has a sidecar
  `.request.json` recording the CDS job ID and the exact request.
- **Elevation:** the 17 GLO-30 tiles required, fetched with
  `elevation.acquire.fetch_tile`.
- **Dataset:** one gitignored Parquet per area in `data/training/stage4/`.
  It uses the unchanged Phase 2D extraction, de-accumulation (over the
  continuous 2021–2023 series), unit conversion and pairing.
- **Records:** `stage4c_acquisition_record.json` (requests, hashes, land/sea)
  and `stage4_dataset_manifest.json` (coverage, corrections, exclusions,
  integrity, hashes, storage).

## Caveats

- DataMeet polygons are 1991-vintage with ±500 m positional error, and form a
  historical village-union spatial proxy, not present-day GP boundaries.
- ERA5/ERA5-Land 2021–2023 availability was verified only for the Yelandur
  area (global products; not re-checked per region).
- Elevation diversity is computed only for candidates fully inside the 4
  GLO-30 tiles on disk; all others are `PENDING_TILE_DOWNLOAD`, although
  every required tile is listed as publicly available.
- Neighbouring ERA5-Land cells are strongly correlated (≥ 0.997 hourly
  temperature correlation within Yelandur), so distinct cells are not fully
  independent samples; an expanded experiment needs spatially blocked folds.
- Cells can span several Taluka Panchayats, so cell groups must be defined
  across candidates, not per candidate.
- The EPSG:32643 centroid projection (UTM 43N) extends slightly beyond its
  zone at Karnataka's eastern edge (~78.6° E); the distortion affects
  centroids by far less than one ERA5-Land cell.
