# Yelandur Historical Village-Union Spatial Proxy — Phase 2C, Stage 6

Research-only. **Not connected to `research/pilot_points.py`, ERA5-Land, or
any downscaling/training code.** No backend code is touched by anything in
this directory.

## What this is — and what it is NOT

Every geometry produced here is a **"historical village-union spatial
proxy"**, also described as a **"1991-vintage spatial proxy derived from
village polygons."** These are the only two labels used anywhere in this
module's output.

This is **never**:
- a current Gram Panchayat boundary
- an official current GP polygon
- a current Panchayat boundary

The underlying village polygons were digitized by hand from **1991** Census
District Handbooks (see `docs/ka/index.html` in the DataMeet source repo),
with a documented **±500m** spatial registration error, and do not reliably
reflect even 2001 boundary changes. Today's Gram Panchayat is a
Panchayati-Raj administrative unit; nothing in this layer was derived from,
or verified against, a current GP boundary survey.

## Source chain

```
LGD current GP
  -> official LGD GP->village mapping        (villages_by_blocks.csv, "Local Body Code")
  -> LGD Census-2001 village code             (villages.csv, "Census 2001 Code")
  -> DataMeet V_CT_CODE (exact crosswalk)     (ka.geojson properties.V_CT_CODE, zero-padded)
  -> DataMeet 1991-vintage village polygon    (ka.geojson properties.geometry)
```

Matching is **code-based only** — no fuzzy matching, no name-similarity
matching, no headquarters-village shortcuts. See `matching.py`'s docstring
for the exact three-tier hierarchy (EXACT_CODE / EXACT_CROSSWALK /
EXACT_NAME) and why, for this dataset, every real match landed in
EXACT_CROSSWALK (DataMeet exposes no Census-2011 code at all, so EXACT_CODE
is structurally unavailable here).

## Scope

| | |
|---|---|
| State | Karnataka, LGD code `29` |
| District (Zila Panchayat) | Chamarajanagar, LGD code `486` |
| Block (Taluka Panchayat) | Yelandur, LGD code `6132` (parent `486`) |
| Subdistrict (village-table join key) | `5578` |
| Gram Panchayats | all 12 real GPs under Taluka Panchayat 6132 — a complete taluk, not a cherry-picked subset |

All four LGD codes above were independently re-verified this session against
`data/raw/lgd/pri_local_bodies.22Sep2026.csv` (not taken on trust from the
task description) — see `build.py::load_official_gp_roster`, which reads
the GP roster straight from `pri_local_bodies.csv` and raises if it doesn't
find exactly 12 GPs under taluka-panchayat code `6132`.

## Files

| File | Committed? | Purpose |
|---|---|---|
| `acquire.py` | Yes | Reproducible fetch of raw LGD + DataMeet sources into `data/raw/` (gitignored) |
| `matching.py` | Yes | Pure code-based village-matching logic, no I/O |
| `build.py` | Yes | Orchestrates fetch -> match -> per-GP union/centroid/area -> writes the committed layer |
| `spatial_proxy_data.py` | Yes | Loader/validator over the committed layer, used by tests and any future consumer |
| `yelandur_spatial_proxy.json` | **Yes** | The derived output: 12 GP records with full provenance metadata + geometry for the 11 GPs where at least one village matched |
| `data/raw/lgd/*.csv` | No (gitignored) | Raw LGD component CSVs, re-downloadable via `acquire.py` |
| `data/raw/datameet/ka.geojson` | **No (gitignored, ~86MB)** | Raw DataMeet Karnataka layer — never committed, per the Stage 6 instruction. Re-downloaded on demand. |
| `data/raw/datameet/provenance_manifest.json` | No (gitignored) | Cached blob SHA / commit SHA for `ka.geojson`, fetched once via the GitHub API |

## Output schema (`yelandur_spatial_proxy.json`)

Top level: `type`, `label`, `vintage`, `terminology_note`, `scope`,
`source_chain`, `matching_methodology`, `coverage_summary`,
`source_provenance`, and `panchayats` (12 records).

Each of the 12 `panchayats` entries carries exactly the fields required by
the Stage 6 implementation spec:

```
state_lgd_code, district_lgd_code, taluka_panchayat_lgd_code,
panchayat_lgd_code, panchayat_name,
expected_village_count, matched_village_count, missing_village_count,
geometry_status  (COMPLETE | PARTIAL | UNAVAILABLE),
geometry_source, geometry_vintage, geometry_basis,
source_license, source_positional_error, source_crs,
source_blob_sha, source_content_commit, source_note,
constituent_villages  (per-village name/codes/match_method/matched flag),
projected_crs_used_for_centroid_area, centroid_wgs84, area_km2,
union_geometry_type, geometry  (GeoJSON geometry dict, or null if UNAVAILABLE)
```

`geometry_status` rules (enforced in `build.py::build_gp_record`, not just
documented):
- **COMPLETE** — every official constituent village has a matched polygon.
- **PARTIAL** — at least one but not all constituent villages matched. The
  union IS still built and stored, but `geometry_basis` explicitly says the
  union **understates** the true historical extent, and `missing_villages`
  lists what's excluded.
- **UNAVAILABLE** — zero constituent villages matched. No geometry, no
  centroid, no area are stored (`geometry`/`centroid_wgs84`/`area_km2` are
  all `null`) — never fabricated.

## CRS handling

The source file declares **no explicit CRS** (no GeoJSON `"crs"` member).
Per RFC 7946 this defaults to WGS84 geographic coordinates, corroborated by
the DataMeet project's own documentation ("reprojected to WGS84 datum and
Geographic projection, units: decimal degrees" — `docs/ka/index.html`).
Stored geometry is preserved in this native WGS84 (lon/lat) representation.

Centroid and area are **not** computed naively in lat/lon degrees (a degree
of longitude is not a fixed physical distance). Both are computed by
reprojecting the unioned polygon to **EPSG:32643 (UTM Zone 43N)** — an
appropriate metric CRS for this longitude band — computing centroid/area
there, then transforming the centroid back to WGS84 for storage
(`centroid_wgs84`). `projected_crs_used_for_centroid_area` records exactly
which CRS was used for this math.

## Geometry validity

Every matched source village polygon and every per-GP union is checked with
`shapely`'s `is_valid`. **No automatic repair (`buffer(0)` or similar) is
applied anywhere.** If any geometry is found invalid, `build.py` raises
immediately with the shapely validity-reason string rather than silently
fixing or dropping it — as of this build, zero invalid geometries were
found among the 26 matched villages or the 11 GP unions.

## Coverage result

```
expected_gp_count:        12
expected_village_count:   28
matched_village_count:    26
complete_gp_count:        10
partial_gp_count:         1   (Agara — Kinakahalli unmatched)
unavailable_gp_count:     1   (Mamballi — its one village, Mamballi, unmatched)
```

`build.py` hard-asserts this exact tuple after every build and raises
(rather than silently adapting) if a re-run against fresh source data ever
produces a different result — see the `STOP:` `RuntimeError` in
`build()`. `Kinakahalli` and `Mamballi` were confirmed absent from
**the entire statewide** `ka.geojson` (29,731 features), not merely
misfiled under a different district/taluk label — this is a genuine
DataMeet coverage gap, not a matching-methodology failure.

## License / attribution (ODbL 1.0)

`datameet/indian_village_boundaries` is licensed under the **Open Data
Commons Open Database License (ODbL) v1.0**. Any public use of this derived
layer must: (1) retain attribution to the DataMeet project and the original
digitizers (CISED, now merged with ATREE); (2) if redistributed as a
database/derivative database, offer it under ODbL or a compatible
share-alike license — "produced works" (rendered maps, aggregate
statistics) may use different terms per ODbL §4.6. This module never
redistributes the raw 86MB source file — only the small, derived,
already-filtered-to-Yelandur layer is committed.

## Reproducing

```bash
pip install -r research/requirements.txt
cd research/spatial_proxy
python build.py
```

Real network calls: downloads ~9MB of LGD `.7z` release assets (if not
already cached in `data/raw/lgd/`) and the ~86MB DataMeet `ka.geojson` (if
not already cached in `data/raw/datameet/`, which is gitignored and never
committed). Both caches are idempotent — re-running `build.py` after the
first successful run makes no further network calls.

## Tests

```bash
cd research && python -m pytest tests/test_spatial_proxy.py -q
```

Tests run against the **committed** `yelandur_spatial_proxy.json`, not a
live rebuild — same convention as `research/admin_identity`'s test suite.

## Exact limitations

- 1991-vintage source geometry with a documented ±500m positional error —
  unsuitable for anything requiring precise boundaries.
- 2 of 28 official villages (`Kinakahalli`, `Mamballi`) have no DataMeet
  polygon anywhere in the state file — a real coverage gap.
- `Mamballi` GP therefore has **no** spatial-proxy geometry at all.
- `Agara` GP's stored union covers only 1 of its 2 constituent villages and
  is explicitly marked `PARTIAL` — it understates the true historical
  extent and must not be treated as complete.
- This layer is not connected to ERA5-Land, elevation, or any downscaling
  code — that remains out of scope until a later, separately-approved
  stage.
