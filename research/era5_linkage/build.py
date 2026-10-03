"""
Builds the Yelandur ERA5-Land SPATIAL LINKAGE artifact
(research/era5_linkage/yelandur_era5_linkage.json) by relating the
EXISTING, UNMODIFIED spatial-proxy geometries/centroids
(research/spatial_proxy/yelandur_spatial_proxy.json) and elevation stats
(research/elevation/yelandur_elevation.json) to the ERA5-Land grid.

This is a SPATIAL LINKAGE artifact, not downscaling and not a forecast --
see README.md and the terminology_note embedded in the output.

ACQUISITION: reuses the ONE existing ERA5-Land acquisition mechanism in
this repo (era5_land/acquire.py's dataset/variable/date constants +
config.get_cds_client()) for a new, small Yelandur-area bounding-box
request. No second acquisition path is created. If CDS credentials are not
configured (the same blocker documented in research/README.md's Phase 2A
status since this pipeline's very first stage), this module does NOT
fabricate a grid -- it records an explicit "BLOCKED_NO_ERA5_GRID_DATA"
linkage_status per GP and a top-level acquisition_status/blocker
explanation, while still populating every field that genuinely does not
require ERA5 grid data (real centroids from the spatial proxy, real
elevation stats, real centroid-to-centroid spatial-variation metrics).
"""

import hashlib
import json
import math
import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from config import MissingCredentialsError, get_cds_client  # noqa: E402
from era5_land.acquire import (  # noqa: E402
    DATASET,
    PILOT_DAYS,
    PILOT_MONTH,
    PILOT_TIMES,
    PILOT_YEAR,
    RAW_OUTPUT_DIR,
    VARIABLES,
)
from era5_land.archive import ensure_netcdf  # noqa: E402
from era5_linkage import linkage  # noqa: E402
from elevation.elevation_data import load_layer as load_elevation  # noqa: E402
from pipeline.coordinates import haversine_km  # noqa: E402
from spatial_proxy.spatial_proxy_data import load_layer as load_spatial_proxy  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent / "yelandur_era5_linkage.json"

# Union bbox of the real spatial-proxy geometries (76.99-77.19E, 11.95-12.15N,
# see research/spatial_proxy/README.md) padded to a round CDS "area" box,
# same [North, West, South, East] convention as era5_land/acquire.py's
# PILOT_AREA.
YELANDUR_AREA = [12.25, 76.90, 11.85, 77.30]
YELANDUR_RAW_PATH = RAW_OUTPUT_DIR / f"era5_land_yelandur_{PILOT_YEAR}{PILOT_MONTH}.nc"

SOURCE = "ERA5-Land (reanalysis-era5-land)"
SOURCE_TYPE = "reanalysis"  # never "observed weather"
TERMINOLOGY_NOTE = (
    "This artifact establishes spatial linkage between historical "
    "village-union spatial proxies and ERA5-Land grid cells. It does not "
    "constitute Panchayat-level downscaling. ERA5-Land values are "
    "reanalysis data, not direct sensor readings. The underlying geometry "
    "is a historical village-union spatial proxy (1991-vintage spatial "
    "proxy derived from village polygons), not a present-day Gram "
    "Panchayat boundary."
)


def attempt_yelandur_era5_acquisition() -> tuple[object | None, str | None]:
    """Attempts a REAL, small ERA5-Land request for the Yelandur bounding
    box, reusing era5_land/acquire.py's exact dataset/variable/date
    constants and config.get_cds_client() -- the one existing acquisition
    mechanism in this repo. Returns (xr.Dataset, None) on success,
    (None, blocker_message) if credentials are missing or the request
    otherwise fails. Never fabricates a dataset on failure."""
    import xarray as xr

    if YELANDUR_RAW_PATH.exists():
        return xr.open_dataset(YELANDUR_RAW_PATH), None

    try:
        client = get_cds_client()
    except MissingCredentialsError as e:
        return None, str(e)

    request = {
        "variable": VARIABLES,
        "year": [PILOT_YEAR],
        "month": [PILOT_MONTH],
        "day": PILOT_DAYS,
        "time": PILOT_TIMES,
        "area": YELANDUR_AREA,
        "data_format": "netcdf",
    }
    try:
        RAW_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        client.retrieve(DATASET, request, str(YELANDUR_RAW_PATH))
        real_path = ensure_netcdf(YELANDUR_RAW_PATH)
        return xr.open_dataset(real_path), None
    except Exception as e:  # real network/CDS failure, not credentials -- still never fabricated
        return None, f"CDS request for the Yelandur area failed: {e}"


def build_grid_metadata(grid_dataset, source_path: Path = YELANDUR_RAW_PATH) -> dict:
    """Describes the grid of the ACTUAL acquired Yelandur-area dataset --
    every value is read from `grid_dataset`'s own coordinate arrays, never
    hardcoded and never taken from another location's file. When no grid
    was acquired, every grid field is null (never fabricated)."""
    if grid_dataset is None:
        return {
            "acquisition_status": "BLOCKED",
            "source_dataset": DATASET,
            "source_file": None,
            "source_file_sha256": None,
            "latitude_order": None, "longitude_order": None,
            "latitude_spacing_deg": None, "longitude_spacing_deg": None,
            "n_latitude": None, "n_longitude": None,
            "latitude_min": None, "latitude_max": None,
            "longitude_min": None, "longitude_max": None,
        }
    source_path = Path(source_path)
    try:
        source_file = source_path.resolve().relative_to(_RESEARCH_DIR.parent).as_posix()
    except ValueError:
        source_file = source_path.name
    return {
        "acquisition_status": "AVAILABLE",
        "source_dataset": DATASET,
        "source_file": source_file,
        "source_file_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        **linkage.describe_grid(grid_dataset["latitude"].values, grid_dataset["longitude"].values),
    }


def build_gp_linkage_record(gp: dict, elev_record: dict | None, grid_dataset, blocker: str | None) -> dict:
    status = gp["geometry_status"]
    base = {
        "panchayat_lgd_code": gp["panchayat_lgd_code"],
        "gp_name": gp["panchayat_name"],
        "coverage_status": status,
    }

    if status == "UNAVAILABLE":
        base.update({
            "centroid_latitude": None, "centroid_longitude": None,
            "nearest_grid_latitude": None, "nearest_grid_longitude": None,
            "latitude_difference_deg": None, "longitude_difference_deg": None,
            "centroid_to_grid_distance_km": None,
            "intersecting_cell_count": None, "intersecting_cells": None,
            "linkage_status": "UNAVAILABLE",
            "elevation_mean_m": None, "elevation_min_m": None,
            "elevation_max_m": None, "elevation_range_m": None,
            "note": (
                "No spatial-proxy geometry is available for this GP "
                f"(missing constituent villages: {gp['missing_villages']}). "
                "No centroid, grid linkage, or elevation is attempted or "
                "inferred -- never fabricated."
            ),
        })
        return base

    centroid = gp["centroid_wgs84"]  # REUSE the existing, already-validated spatial-proxy centroid
    base["centroid_latitude"] = centroid["lat"]
    base["centroid_longitude"] = centroid["lon"]

    if grid_dataset is None:
        base.update({
            "nearest_grid_latitude": None, "nearest_grid_longitude": None,
            "latitude_difference_deg": None, "longitude_difference_deg": None,
            "centroid_to_grid_distance_km": None,
            "intersecting_cell_count": None, "intersecting_cells": None,
            "linkage_status": "BLOCKED_NO_ERA5_GRID_DATA",
            "note": (
                f"ERA5-Land grid data for the Yelandur AOI could not be "
                f"acquired this session ({blocker}). The centroid above is "
                f"real (reused from the spatial proxy{', PARTIAL geometry only' if status == 'PARTIAL' else ''}); "
                f"grid-linkage fields are null, not fabricated or estimated "
                f"from a different location's grid."
            ),
        })
    else:
        nearest = linkage.nearest_grid_cell(grid_dataset, centroid["lat"], centroid["lon"])
        base.update(nearest)
        cells = linkage.cells_intersecting_geometry(
            gp["geometry"], grid_dataset["latitude"].values, grid_dataset["longitude"].values
        )
        base["intersecting_cell_count"] = len(cells)
        base["intersecting_cells"] = cells
        if len(cells) == 0:
            base["linkage_status"] = "NO_INTERSECTION"
        elif len(cells) == 1:
            base["linkage_status"] = "SINGLE_CELL"
        else:
            base["linkage_status"] = "MULTI_CELL"
        coverage_note = "PARTIAL geometry only (missing villages excluded)" if status == "PARTIAL" else "full GP union"
        base["note"] = f"Computed from the spatial proxy's {coverage_note}."

    if elev_record is not None:
        base["elevation_mean_m"] = elev_record["mean_m"]
        base["elevation_min_m"] = elev_record["min_m"]
        base["elevation_max_m"] = elev_record["max_m"]
        base["elevation_range_m"] = elev_record["range_m"]
    else:
        base["elevation_mean_m"] = base["elevation_min_m"] = None
        base["elevation_max_m"] = base["elevation_range_m"] = None

    return base


def _pairwise_centroid_distances(available_gps: list[dict]) -> list[tuple[str, str, float]]:
    pairs = []
    for i in range(len(available_gps)):
        for j in range(i + 1, len(available_gps)):
            a, b = available_gps[i], available_gps[j]
            ca, cb = a["centroid_wgs84"], b["centroid_wgs84"]
            d = haversine_km(ca["lat"], ca["lon"], cb["lat"], cb["lon"])
            pairs.append((a["panchayat_name"], b["panchayat_name"], d))
    return pairs


def compute_spatial_variation_audit(spatial_proxy: dict, elevation: dict, grid_dataset, blocker: str | None) -> dict:
    available_gps = [gp for gp in spatial_proxy["panchayats"] if gp["geometry_status"] != "UNAVAILABLE"]
    complete_gps = [gp for gp in spatial_proxy["panchayats"] if gp["geometry_status"] == "COMPLETE"]

    lats = [gp["centroid_wgs84"]["lat"] for gp in available_gps]
    lons = [gp["centroid_wgs84"]["lon"] for gp in available_gps]
    lat_extent_deg = max(lats) - min(lats)
    lon_extent_deg = max(lons) - min(lons)

    pairwise = _pairwise_centroid_distances(available_gps)
    nn_separation_km = {}
    for gp in available_gps:
        name = gp["panchayat_name"]
        dists = [d for a, b, d in pairwise if a == name or b == name]
        nn_separation_km[name] = min(dists)
    min_pair = min(pairwise, key=lambda t: t[2])
    max_pair = max(pairwise, key=lambda t: t[2])

    elev_by_name = {gp["gp_name"]: gp for gp in elevation["panchayats"]}
    complete_means = [
        elev_by_name[gp["panchayat_name"]]["mean_m"]
        for gp in complete_gps
        if elev_by_name[gp["panchayat_name"]]["mean_m"] is not None
    ]
    elevation_range_across_complete = (
        {
            "min_mean_m": min(complete_means),
            "max_mean_m": max(complete_means),
            "spread_m": max(complete_means) - min(complete_means),
            "n_gps": len(complete_means),
        }
        if complete_means else None
    )

    if grid_dataset is not None:
        cell_by_gp = {}
        for gp in available_gps:
            centroid = gp["centroid_wgs84"]
            nearest = linkage.nearest_grid_cell(grid_dataset, centroid["lat"], centroid["lon"])
            cell_by_gp[gp["panchayat_name"]] = (nearest["nearest_grid_latitude"], nearest["nearest_grid_longitude"])
        distinct_cells = sorted(set(cell_by_gp.values()))
        cells_to_gps: dict = {}
        for name, cell in cell_by_gp.items():
            cells_to_gps.setdefault(cell, []).append(name)
        era5_distribution = {
            "status": "COMPUTED",
            "distinct_cell_count": len(distinct_cells),
            "distinct_cells": [{"latitude": c[0], "longitude": c[1]} for c in distinct_cells],
            "gps_per_cell": {f"{lat},{lon}": names for (lat, lon), names in cells_to_gps.items()},
            "all_gps_collapse_onto_one_cell": len(distinct_cells) == 1,
        }
    else:
        approx_lat_km = lat_extent_deg * 111.0
        approx_lon_km = lon_extent_deg * 111.0 * math.cos(math.radians(sum(lats) / len(lats)))
        era5_distribution = {
            "status": "BLOCKED_NO_ERA5_GRID_DATA",
            "distinct_cell_count": None,
            "distinct_cells": None,
            "gps_per_cell": None,
            "all_gps_collapse_onto_one_cell": None,
            "note": (
                f"Cannot determine the actual distinct ERA5-Land cell count "
                f"or whether GPs collapse onto one cell without real "
                f"Yelandur-area grid data ({blocker}). Context only, NOT a "
                f"confirmed result: ERA5-Land's documented native "
                f"resolution is ~0.1 degree (~9-11 km); this AOI's real "
                f"centroid extent is ~{lat_extent_deg:.3f} deg lat x "
                f"{lon_extent_deg:.3f} deg lon (~{approx_lat_km:.1f} km x "
                f"~{approx_lon_km:.1f} km), which is PLAUSIBLY within a "
                f"small number of ERA5-Land cells given that resolution -- "
                f"an expectation based on known ERA5-Land resolution, not a "
                f"verified finding."
            ),
        }

    return {
        "available_gp_count": len(available_gps),
        "complete_gp_count": len(complete_gps),
        "centroid_latitude_extent_deg": lat_extent_deg,
        "centroid_longitude_extent_deg": lon_extent_deg,
        "centroid_nearest_neighbor_separation_km": nn_separation_km,
        "centroid_min_pairwise_distance_km": {"gp_a": min_pair[0], "gp_b": min_pair[1], "distance_km": min_pair[2]},
        "centroid_max_pairwise_distance_km": {"gp_a": max_pair[0], "gp_b": max_pair[1], "distance_km": max_pair[2]},
        "elevation_mean_range_across_complete_gps": elevation_range_across_complete,
        "era5_grid_cell_distribution": era5_distribution,
    }


def build() -> dict:
    spatial_proxy = load_spatial_proxy()  # read-only; never modified
    elevation = load_elevation()  # read-only; never modified
    elevation_by_gp_id = {gp["gp_id"]: gp for gp in elevation["panchayats"]}

    grid_dataset, blocker = attempt_yelandur_era5_acquisition()

    gp_records = [
        build_gp_linkage_record(gp, elevation_by_gp_id.get(gp["panchayat_lgd_code"]), grid_dataset, blocker)
        for gp in spatial_proxy["panchayats"]
    ]
    gp_records.sort(key=lambda r: r["gp_name"])

    n_complete = sum(1 for r in gp_records if r["coverage_status"] == "COMPLETE")
    n_partial = sum(1 for r in gp_records if r["coverage_status"] == "PARTIAL")
    n_unavailable = sum(1 for r in gp_records if r["coverage_status"] == "UNAVAILABLE")
    expected = (10, 1, 1)
    actual = (n_complete, n_partial, n_unavailable)
    if actual != expected:
        raise RuntimeError(
            f"STOP: coverage tally diverged from the spatial proxy's own "
            f"coverage (expected COMPLETE/PARTIAL/UNAVAILABLE={expected}, "
            f"got {actual}). The spatial proxy is the source of truth here."
        )

    audit = compute_spatial_variation_audit(spatial_proxy, elevation, grid_dataset, blocker)

    output = {
        "type": "YelandurEra5LandSpatialLinkage",
        "dataset_label": "Yelandur ERA5-Land spatial linkage",
        "source": SOURCE,
        "source_type": SOURCE_TYPE,
        "spatial_proxy_source": "research/spatial_proxy/yelandur_spatial_proxy.json (read-only; not modified)",
        "spatial_proxy_vintage": spatial_proxy["vintage"],
        "elevation_source": "research/elevation/yelandur_elevation.json (read-only; not modified; referenced, not duplicated)",
        "methodology": (
            "Centroid link: nearest ERA5-Land grid cell to each GP's existing "
            "spatial-proxy centroid, via pipeline.coordinates.nearest_gridpoint "
            "(xarray .sel(method='nearest')) + haversine_km -- the same "
            "existing coordinate utility used by the Phase 2A/2B normalization "
            "pipeline, not a second implementation. Geometry intersection: grid "
            "cells are CENTER points; cell polygons are derived from midpoints "
            "to neighboring centers (era5_linkage/linkage.py:_cell_edges_1d), "
            "with the outermost cell on each axis mirroring its one real "
            "interior half-width outward -- never an assumed spacing. A cell "
            "is 'intersecting' if its derived polygon intersects the GP "
            "geometry (shapely .intersects), evaluated in native WGS84 -- no "
            "reprojection, since intersection topology is unaffected by it."
        ),
        "terminology_note": TERMINOLOGY_NOTE,
        "grid_metadata": build_grid_metadata(grid_dataset),
        "acquisition_status": "AVAILABLE" if grid_dataset is not None else "BLOCKED",
        "acquisition_blocker": blocker,
        "coverage_summary": {
            "expected_gp_count": 12,
            "complete_gp_count": n_complete,
            "partial_gp_count": n_partial,
            "unavailable_gp_count": n_unavailable,
        },
        "spatial_variation_audit": audit,
        "panchayats": gp_records,
    }

    if grid_dataset is not None:
        grid_dataset.close()

    return output


if __name__ == "__main__":
    result = build()
    OUTPUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    print(f"acquisition_status: {result['acquisition_status']}")
    if result["acquisition_blocker"]:
        print(f"acquisition_blocker: {result['acquisition_blocker']}")
    print(f"Coverage: {result['coverage_summary']}")
