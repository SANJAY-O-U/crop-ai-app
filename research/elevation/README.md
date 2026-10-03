# Yelandur Elevation Context — Phase 2C

Research-only. **Not connected to ERA5-Land, `research/pilot_points.py`, or
`research/pipeline/training_pairs.py`.** No backend/frontend code is
touched by anything in this directory. This phase establishes a
contextual elevation layer only — it makes **no claim** that elevation
improves downscaling accuracy, and no model has been trained or evaluated
using it.

## Why elevation is being added

The next pipeline stage (multi-Panchayat training/evaluation dataset) will
need per-GP terrain context alongside ERA5-Land weather. Before any
weather linkage happens, this stage attaches reproducible, auditable
elevation statistics to the **existing, unmodified** Yelandur spatial
proxy (`research/spatial_proxy/yelandur_spatial_proxy.json`), so later
stages have a real, source-verified elevation feature to draw on instead
of inventing one later under time pressure.

## What this is — and what it is NOT

Elevation statistics here describe the terrain under a **"historical
village-union spatial proxy"** (**"1991-vintage spatial proxy derived from
village polygons"**) — never a present-day Gram Panchayat boundary. The
spatial-proxy geometry itself is untouched; this module only reads it.

## Elevation source

| | |
|---|---|
| Dataset | **Copernicus DEM GLO-30** |
| Type | Digital Surface Model (DSM) — includes buildings/vegetation/infrastructure, not bare-earth |
| Nominal resolution | ~30 m (native pixel spacing: 1 arc-second ≈ 30.87 m N–S; ≈30.2 m E–W at Yelandur's latitude, ~12°N) |
| Horizontal CRS | EPSG:4326 (WGS84), confirmed via `rasterio.open(...).crs` on the downloaded tiles |
| Vertical unit | metres |
| Vintage | Copernicus DEM 2021 release |
| Access mechanism | AWS Registry of Open Data, `s3://copernicus-dem-30m` (region `eu-central-1`), public read, **no AWS account or credentials required** |
| Registry page | <https://registry.opendata.aws/copernicus-dem/> |
| Bucket documentation | <https://copernicus-dem-30m.s3.amazonaws.com/readme.html> |
| License | Free for general public use — <https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM> |
| Managed by | Sinergise, on behalf of the Copernicus Programme |

### Why this access mechanism, and not something else

This session inspected the official access options before writing any
acquisition code:

- The **AWS Open Data bucket** is documented on the ESA-recognized AWS
  Registry of Open Data page, requires no registration, no API key, and no
  Copernicus Data Space Ecosystem account. Verified this session with
  `curl -I` against the actual tile URLs: `200 OK`, `Accept-Ranges: bytes`,
  no auth headers needed.
- The bucket publishes its **own authoritative `tileList.txt`** of every
  publicly-released GLO-30 tile — `acquire.py` downloads and checks this
  list before attempting any tile fetch, so a genuinely unreleased tile
  fails loudly (`DemAcquisitionBlocked`) instead of silently 403ing or
  silently falling back to GLO-90.
- No endpoint here was guessed or scraped from an undocumented page — the
  tile-naming convention (`Copernicus_DSM_COG_10_{northing}_00_{easting}_00_DEM`)
  is taken verbatim from the bucket's own `readme.html`.

**Result: all 4 tiles needed for Yelandur's full spatial-proxy extent are
publicly available.** No blocker was hit; GLO-30 was acquired exactly as
specified, with no substitution.

## Directory structure

```
research/elevation/
├── __init__.py
├── acquire.py            # tile discovery (tileList.txt) + HTTPS download into data/raw/elevation/
├── extract.py             # zonal-statistics methodology + computation
├── build.py                # orchestrates acquire -> extract -> validate -> write
├── elevation_data.py     # loader/validator for the committed output
├── README.md              # this file
└── yelandur_elevation.json  # committed derived output (small — stats only, no raster)
```

Raw DEM tiles are cached under `data/raw/elevation/` (gitignored via the
existing `data/raw/**` rule — same convention as `data/raw/lgd/` and
`data/raw/datameet/`). **The raw DEM is never committed.**

## Which tiles Yelandur actually needs

Some Yelandur GP polygons (`Duggatti`, `Honnuru`) extend slightly west of
77.0°E, so the required tile set is **not** just `N11/E077` + `N12/E077` —
it also includes `N11/E076` and `N12/E076`. `build.py` computes this
correctly by taking the union bounding box of every available spatial-proxy
geometry (not a hand-picked guess), so this is discovered automatically
rather than hardcoded.

## Join key

Every elevation record is joined to its spatial-proxy GP by
**`panchayat_lgd_code`** (stored as `gp_id` in the output) — never by
name. No fuzzy matching is used anywhere in this module.

## Extraction methodology (exact)

See `extract.py`'s module docstring for the full, authoritative version.
Summary:

- **CRS transformation**: none. Both the DEM (EPSG:4326) and the
  spatial-proxy geometries (also WGS84) are already in the same CRS.
  Elevation statistics (mean/min/max/std) are reprojection-invariant, so no
  projected CRS is required for correctness. (If a physical area/distance
  were ever needed here, EPSG:32643 / UTM 43N is the appropriate choice —
  same convention `research/spatial_proxy/build.py` already uses.)
- **Pixel inclusion**: pixel-**center** based (`rasterstats` default,
  `all_touched=False`). A DEM pixel counts toward a GP's sample iff that
  pixel's center falls inside the polygon — not area/intersection-weighted.
  This avoids double-counting boundary pixels shared between adjacent GPs.
- **nodata handling**: the downloaded COG tiles carry no embedded GDAL
  nodata tag, and were scanned for common DSM sentinel values (-32767,
  -9999); none found (observed tile-wide minimum: +112 m). `rasterstats`
  itself requires some nodata value for its internal masking machinery, so
  `-999` is passed explicitly — this never collides with real elevation in
  this inland AOI, so it is functionally "no masking."
- **Units**: metres, unconverted from the DEM's native unit.
- **sample_count**: the literal count of ~30 m pixel centers inside the
  polygon (COMPLETE/PARTIAL GPs only).

## COMPLETE / PARTIAL / UNAVAILABLE semantics

`coverage_status` mirrors the spatial proxy's own `geometry_status`
**exactly**, joined by `panchayat_lgd_code`:

- **COMPLETE** — normal elevation statistics, sampled from the GP's full
  stored union.
- **PARTIAL** (`Agara`) — statistics sampled **only** from the geometry
  actually present in the spatial proxy (1 of its 2 constituent villages).
  The missing village (`Kinakahalli`) is never inferred, estimated, or
  substituted — its absence is recorded in `note`, and the resulting
  statistics describe only the covered area.
- **UNAVAILABLE** (`Mamballi`) — no DEM sampling is attempted at all. Every
  numeric field (`mean_m`, `min_m`, `max_m`, `range_m`, `std_m`,
  `sample_count`) is JSON `null` — never a fabricated zero, never inferred
  from neighboring GPs.

## Output schema (`yelandur_elevation.json`)

Top level: `type`, `dataset_label`, `source`, `source_type`, `vintage`,
`resolution_m`, `horizontal_crs`, `vertical_unit`, `methodology`,
`terminology_note`, `source_provenance` (registry/bucket/license URLs +
exact tiles used), `coverage_summary`, `panchayats` (12 records).

Each panchayat record: `gp_id`, `gp_name`, `coverage_status`, `source`,
`source_type`, `resolution_m`, `horizontal_crs`, `vertical_unit`,
`methodology`, `spatial_proxy_geometry_source`,
`spatial_proxy_geometry_vintage`, `mean_m`, `min_m`, `max_m`, `range_m`,
`std_m`, `sample_count`, `note`.

## Reproducing

```bash
pip install -r research/requirements.txt
cd research/elevation
python build.py
```

Real network calls: downloads the required Copernicus DEM GLO-30 tiles
(~40 MB each, 4 tiles ≈ 165 MB total) from the public AWS bucket into
`data/raw/elevation/` (gitignored, idempotent — already-cached tiles are
not re-downloaded), then samples them against the read-only spatial proxy
and writes `yelandur_elevation.json`. No credentials or manual Copernicus
registration are required for this access path.

`build.py` hard-asserts the expected COMPLETE/PARTIAL/UNAVAILABLE tally
(10/1/1) against the spatial proxy's own coverage and raises a `STOP:`
error rather than silently continuing if it ever diverges — the spatial
proxy is the single source of truth for which GPs have geometry at all.

## Tests

```bash
cd research && python -m pytest tests/test_elevation.py -q
```

Tests run against the **committed** `yelandur_elevation.json`, same
convention as `test_spatial_proxy.py` and `test_admin_identity.py`.

## Limitations

- Copernicus DEM GLO-30 is a **Digital Surface Model**, not bare-earth —
  statistics include building/canopy height where present, which matters
  most for the forested Biligiri Ranganabetta GP.
- `Mamballi` has no elevation context at all — it inherits the spatial
  proxy's own coverage gap, not a new one introduced here.
- `Agara`'s statistics describe only its 1-of-2 matched villages; treating
  them as representative of the full GP would understate the true
  elevation range.
- Pixel-center inclusion (not area-weighted) means very small or
  sliver-shaped polygon edges may be under- or over-represented by a
  handful of pixels at GP boundaries.
- This is a **contextual layer only**: no claim is made, tested, or
  implied here about whether elevation improves downscaling accuracy, and
  no model has been trained. That evaluation is out of scope until a
  later, separately-approved stage — and even then, it comes only after
  the still-pending ERA5-Land spatial linkage.
