# Yelandur ERA5-Land Spatial Linkage — Phase 2C

Research-only. **This artifact establishes spatial linkage between
historical village-union spatial proxies and ERA5-Land grid cells. It does
not constitute Panchayat-level downscaling.** No model is trained, no
prediction is made, and no accuracy claim exists anywhere in this module.

## Purpose

The next pipeline stage (multi-Panchayat training/evaluation dataset) needs
to know, per GP, which ERA5-Land grid cell(s) it actually relates to before
any weather values are joined in. This stage answers that — and only
that — question, reproducibly and auditably, for all 12 Yelandur GPs.

## Terminology (enforced, not just documented)

| Say | Never say |
|---|---|
| "historical village-union spatial proxy" | "current Gram Panchayat boundary" |
| "reanalysis data" | "observed weather" |
| "ERA5-Land spatial linkage" | "Panchayat-level forecast" |

## Audit of existing infrastructure (done before writing any new code)

- **`research/era5_land/acquire.py`**: the ONE existing ERA5-Land
  acquisition mechanism — `config.get_cds_client()` + a `dataset =
  "reanalysis-era5-land"` request with an explicit `area` bounding box.
  Reused directly (`DATASET`, `VARIABLES`, `PILOT_YEAR/MONTH/DAYS/TIMES`,
  `RAW_OUTPUT_DIR`) — no second acquisition path was created.
- **`research/era5_land/archive.py`**: `ensure_netcdf()` (ZIP-wrapper
  handling) reused as-is for any new download.
- **`research/pipeline/coordinates.py`**: `nearest_gridpoint()` and
  `haversine_km()` reused directly for the centroid link (Part A) — not
  reimplemented.
- **`research/pipeline/normalize.py` / `units.py`**: inspected for
  precipitation semantics and variable naming; **untouched**. This module
  never needs per-timestep values, so precipitation de-accumulation is out
  of scope here — its existing behavior is preserved exactly as-is.
- **Confirmed grid convention** (from the one real ERA5-Land file already
  in this repo, `data/raw/era5_land/era5_land_pilot_202306.nc`):
  latitude **descending** (13.5 → 13.3), longitude **ascending** (77.5 →
  77.9), uniform **0.1°** spacing both axes, CRS implicitly WGS84
  (lat/lon in degrees, no separate CRS metadata on the NetCDF — standard
  for CDS-delivered ERA5-Land). Grid values are **cell centers**, not
  polygon edges — see "Grid interpretation" below.

## Current inputs (read-only)

- `research/spatial_proxy/yelandur_spatial_proxy.json` — geometry,
  `centroid_wgs84`, and `geometry_status` per GP. **Not modified.**
- `research/elevation/yelandur_elevation.json` — `mean_m`/`min_m`/`max_m`/
  `range_m` per GP, referenced by `gp_id`, never duplicated wholesale. **Not
  modified.**

## Acquisition attempt (real, not simulated)

`build.py` makes a **real** attempt to acquire ERA5-Land data for a new,
small Yelandur-area bounding box (`[12.25, 76.90, 11.85, 77.30]`, North/
West/South/East — padding the real spatial-proxy geometries' bbox), reusing
`era5_land/acquire.py`'s exact request pattern. This session, that attempt
is **blocked**: no `CDSAPI_KEY` environment variable and no `~/.cdsapirc`
are configured in this environment — the *same* credential gap
`research/README.md`'s Phase 2A section has documented since this
pipeline's first stage, now hit again for a new bounding box.

**This module does not substitute a different DEM-style workaround, does
not reuse the existing (geographically unrelated) Bangalore-area pilot file
as if it were Yelandur's grid, and does not fabricate grid coordinates.**
Instead:

- `acquisition_status: "BLOCKED"` and `acquisition_blocker: "<real error
  message>"` are recorded at the top level.
- Every GP's `linkage_status` is `"BLOCKED_NO_ERA5_GRID_DATA"` (COMPLETE/
  PARTIAL GPs) or `"UNAVAILABLE"` (Mamballi) — grid-dependent fields
  (`nearest_grid_latitude/longitude`, distances, `intersecting_cells`) are
  all JSON `null`.
- Everything that does **not** require ERA5 grid data is still computed
  for real: centroids (reused from the spatial proxy), elevation stats
  (reused from the elevation layer), and the centroid-to-centroid spatial-
  variation metrics in `spatial_variation_audit` (see below).
- `grid_metadata` is derived only from the acquired Yelandur-area NetCDF
  (counts, min/max, ordering, spacing, source file + SHA-256). When
  acquisition is blocked, its grid fields are `null` — no other location's
  grid is ever substituted.

**If a human configures `CDSAPI_KEY` (see `research/README.md`, "Getting
CDS credentials") and re-runs `build.py`, it will make the real request,
cache the result at `data/raw/era5_land/era5_land_yelandur_202306.nc`
(gitignored), and populate every grid-dependent field for real** — no code
change is needed for that to happen; the blocked path and the success path
are the same function (`attempt_yelandur_era5_acquisition`).

## Grid interpretation

ERA5-Land grid coordinates are **cell centers**, not polygon corners. A
value like `latitude=13.4` names the middle of a ~0.1°×0.1° cell, not an
edge. `linkage.py`'s `_cell_edges_1d()` derives each cell's edges from the
midpoints to its neighboring centers:

- **Interior points**: edges are the midpoints to the immediate neighbor on
  each side (standard 1D Voronoi/Thiessen construction).
- **Outermost points** (first/last on either axis): only one real neighbor
  exists. The one derivable edge (midpoint to that neighbor) is kept; the
  other edge is constructed by mirroring that same real half-width
  outward — an explicit, documented convention, never a silently assumed
  spacing and never a shifted coordinate.

Verified deterministic and tested against the real reference grid (see
Tests below): the same `(lat_values, lon_values, lat_idx, lon_idx)` always
produces the same polygon.

## Centroid linkage methodology (Part A)

For each GP with available geometry (`COMPLETE` or `PARTIAL`):
1. Take the existing `centroid_wgs84` already computed and validated in the
   spatial proxy (never recomputed here — "do not duplicate the spatial
   proxy source data unnecessarily").
2. Call `pipeline.coordinates.nearest_gridpoint()` (existing code) to find
   the nearest actual grid-cell center via `xarray .sel(method="nearest")`.
3. `latitude_difference_deg` / `longitude_difference_deg` = centroid minus
   nearest grid center (signed).
4. `centroid_to_grid_distance_km` = `haversine_km()` (existing code) between
   the centroid and that nearest grid center — an explicit geodesic
   calculation, not a flat-plane approximation.

## Geometry intersection methodology (Part B)

For each GP with available geometry, every candidate grid cell (bbox-
prefiltered against the geometry's bounds for efficiency) has its derived
polygon tested with `shapely.Polygon.intersects()` against the GP geometry.
No reprojection is applied — both the GP geometry and the DEM/ERA5 grid are
native WGS84, and intersection topology (which polygons touch which) is
unaffected by using degrees instead of a projected CRS here (unlike an area
calculation, which *would* need one — see `spatial_proxy/README.md` and
`elevation/README.md` for where that distinction actually matters).

`intersecting_cell_count` and `intersecting_cells` are always mutually
consistent by construction (`count == len(cells)`); `linkage_status` is set
from that count: `NO_INTERSECTION` (0), `SINGLE_CELL` (1), `MULTI_CELL`
(2+) — kept as a **separate field** from `coverage_status`, exactly so
multi-cell geometry detail never overloads the spatial-proxy coverage
semantics.

## Coverage semantics

Mirrors the spatial proxy's `geometry_status` exactly, joined by
`panchayat_lgd_code` (never by name — no fuzzy matching anywhere in this
module):

- **COMPLETE** — full GP union geometry used for linkage.
- **PARTIAL** (`Agara`) — linkage computed **only** from the geometry
  actually present in the spatial proxy (1 of 2 constituent villages); the
  missing village (`Kinakahalli`) is never inferred.
- **UNAVAILABLE** (`Mamballi`) — no geometry, no centroid, no grid linkage
  at all. Every numeric field is `null`.

## Reproducing

```bash
pip install -r research/requirements.txt
python research/era5_linkage/build.py
```

Uses existing ERA5-Land data where available (`data/raw/era5_land/`,
gitignored); if a Yelandur-area file is not already cached, it attempts
the **same** CDS acquisition mechanism `era5_land/acquire.py` already
uses. If `CDSAPI_KEY`/`~/.cdsapirc` are not configured, the build
completes anyway with an honestly `BLOCKED` linkage (see above) rather
than failing or fabricating data.

## Tests

```bash
cd research && python -m pytest tests/test_era5_linkage.py -q
```

Two kinds of tests:
1. **Contract tests** against the committed `yelandur_era5_linkage.json`
   (coverage tally, no-fabrication invariants, join-key correctness,
   terminology).
2. **Real, deterministic unit tests of `linkage.py`'s pure functions**
   (nearest-cell lookup, cell-polygon construction, grid-order/spacing
   inference) against `research/synthetic_fixtures.py`'s existing 0.1°
   fixture grid — the same fixture `test_coordinates.py` already uses, so
   these tests exercise real, working spatial-linkage logic even while the
   Yelandur-specific acquisition itself is blocked on credentials.

## Relationship to Phase 2B

Phase 2B's pilot (`research/pilot_points.py`, `research/pipeline/
training_pairs.py`) is a **separate, still-untouched** demo dataset near
Bangalore (13.3–13.5°N, 77.5–77.9°E) — geographically unrelated to
Yelandur (11.95–12.15°N, 76.99–77.19°E). Nothing in this module reads,
writes, or depends on Phase 2B's training-pair code or its downloaded
file.

## Limitations

- **Numeric grid linkage is blocked** this session: no CDS credentials
  configured. `nearest_grid_latitude/longitude`, distances, and
  `intersecting_cells` are `null` for all 11 available GPs. Centroids,
  elevation references, and centroid-to-centroid spatial-variation metrics
  are real.
- The `spatial_variation_audit.era5_grid_cell_distribution` note offers a
  resolution-based *expectation* (ERA5-Land's ~0.1°/~9–11 km cells vs. this
  AOI's ~12.6 km × ~16.4 km centroid extent) — explicitly labeled as
  context, not a confirmed result, since no real grid was available to
  confirm it.
- `Agara`'s linkage (once unblocked) will only ever reflect its 1-of-2
  matched village geometry — same limitation the spatial proxy and
  elevation layers already carry forward.
- `Mamballi` has no linkage at all, by design — never inferred from
  neighboring GPs.
- This is a **spatial linkage** artifact only. No downscaling, no model
  training, no accuracy claim exists here or is implied by anything in
  this module.
