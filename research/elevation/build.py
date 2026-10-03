"""
Builds the Yelandur elevation-context layer
(research/elevation/yelandur_elevation.json) by sampling Copernicus DEM
GLO-30 against the EXISTING, UNMODIFIED spatial-proxy geometries in
research/spatial_proxy/yelandur_spatial_proxy.json.

This is a CONTEXTUAL layer only -- it does not connect to ERA5-Land, does
not feed any training pipeline, and makes no claim about whether elevation
improves downscaling accuracy. See README.md.

Coverage rules (mirrors the spatial proxy's own geometry_status exactly --
joined by panchayat_lgd_code, never by name):

  spatial-proxy geometry_status COMPLETE   -> coverage_status COMPLETE,
      normal elevation statistics sampled from that GP's full stored union.
  spatial-proxy geometry_status PARTIAL    -> coverage_status PARTIAL,
      statistics sampled ONLY from the geometry actually present in the
      spatial proxy (i.e. Agara's 1-of-2-village union) -- the missing
      village's elevation is never inferred or estimated.
  spatial-proxy geometry_status UNAVAILABLE -> coverage_status UNAVAILABLE,
      no DEM sampling is attempted at all; every statistic is JSON null.
"""

import json
import sys
from pathlib import Path

import shapely.geometry as sgeom

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from elevation.acquire import (  # noqa: E402
    LICENSE_URL,
    REGISTRY_URL,
    fetch_tiles_for_bbox,
)
from elevation.extract import DEM_NODATA, compute_zonal_stats, load_mosaic  # noqa: E402
from spatial_proxy.spatial_proxy_data import load_layer as load_spatial_proxy  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent / "yelandur_elevation.json"

DEM_SOURCE = "Copernicus DEM GLO-30"
DEM_SOURCE_TYPE = "Digital Surface Model (DSM)"
DEM_RESOLUTION_M = 30  # nominal; native pixel spacing is 1 arc-second (~30.87m N-S at this latitude)
DEM_HORIZONTAL_CRS = "EPSG:4326 (WGS84)"
DEM_VERTICAL_UNIT = "metres"
DEM_VINTAGE = "Copernicus DEM 2021 release (as distributed via the AWS Open Data bucket)"

METHODOLOGY = (
    "Zonal statistics computed with rasterstats.zonal_stats against a "
    "Copernicus DEM GLO-30 raster mosaic, using each GP's EXISTING "
    "spatial-proxy geometry unmodified. Pixel-CENTER inclusion "
    "(all_touched=False): a DEM pixel counts toward a GP's sample iff that "
    "pixel's center falls inside the polygon. No CRS reprojection is "
    "applied -- DEM and polygon are both native WGS84 (EPSG:4326); "
    "elevation statistics are reprojection-invariant so this is sufficient "
    "for correctness (see extract.py for the full methodology docstring). "
    "No real nodata masking applies: the source COG tiles carry no embedded "
    "nodata tag and were scanned for common DSM sentinel values with none "
    "found for this inland AOI (tile-wide minimum +112m); -999 is passed "
    "only to satisfy rasterstats' own required-sentinel argument and never "
    "collides with real elevation here. sample_count is the literal number "
    "of ~30m pixel centers inside the polygon."
)

TERMINOLOGY_NOTE = (
    "Elevation statistics in this layer are attached to a historical "
    "village-union spatial proxy (1991-vintage spatial proxy derived from "
    "village polygons), NOT to a present-day Gram Panchayat boundary. "
    "Elevation here is a contextual feature only -- this phase makes no "
    "claim that elevation improves downscaling accuracy, and no model has "
    "been trained or evaluated using it."
)


def _license_note() -> str:
    return (
        f"Copernicus DEM GLO-30 Public is free for general public use under "
        f"the terms at {LICENSE_URL}. Distributed via the AWS Registry of "
        f"Open Data ({REGISTRY_URL}), managed by Sinergise on behalf of the "
        f"Copernicus Programme. No attribution string is mandated by the "
        f"license beyond citing the source as done here."
    )


def _bbox_of_geometry(geometry: dict) -> tuple[float, float, float, float]:
    return sgeom.shape(geometry).bounds  # (minx, miny, maxx, maxy)


def _union_bbox(bboxes: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    minx = min(b[0] for b in bboxes)
    miny = min(b[1] for b in bboxes)
    maxx = max(b[2] for b in bboxes)
    maxy = max(b[3] for b in bboxes)
    return minx, miny, maxx, maxy


def _validate_stats(gp_name: str, stats: dict, tolerance: float = 1e-6):
    if stats["sample_count"] == 0:
        for k in ("mean_m", "min_m", "max_m", "range_m", "std_m"):
            assert stats[k] is None, f"{gp_name}: {k} should be null for a zero-sample result"
        return

    mean_m, min_m, max_m, range_m, std_m, count = (
        stats["mean_m"], stats["min_m"], stats["max_m"],
        stats["range_m"], stats["std_m"], stats["sample_count"],
    )
    for label, v in (("mean_m", mean_m), ("min_m", min_m), ("max_m", max_m),
                     ("range_m", range_m), ("std_m", std_m)):
        if v is not None and not (v == v and abs(v) != float("inf")):  # NaN/inf check w/o importing math
            raise RuntimeError(f"STOP: non-finite {label}={v} for GP {gp_name}")

    if not (min_m <= mean_m <= max_m):
        raise RuntimeError(f"STOP: min<=mean<=max violated for {gp_name}: {min_m}<= {mean_m} <={max_m}")
    if abs(range_m - (max_m - min_m)) > tolerance:
        raise RuntimeError(f"STOP: range_m mismatch for {gp_name}: {range_m} != {max_m}-{min_m}")
    if count <= 0:
        raise RuntimeError(f"STOP: sample_count must be positive when statistics exist ({gp_name})")


def build_gp_elevation_record(gp: dict, mosaic_array, transform) -> dict:
    spatial_status = gp["geometry_status"]

    base = {
        "gp_id": gp["panchayat_lgd_code"],
        "gp_name": gp["panchayat_name"],
        "coverage_status": spatial_status,  # mirrors spatial-proxy status exactly
        "source": DEM_SOURCE,
        "source_type": DEM_SOURCE_TYPE,
        "resolution_m": DEM_RESOLUTION_M,
        "horizontal_crs": DEM_HORIZONTAL_CRS,
        "vertical_unit": DEM_VERTICAL_UNIT,
        "methodology": METHODOLOGY,
        "spatial_proxy_geometry_source": gp["geometry_source"],
        "spatial_proxy_geometry_vintage": gp["geometry_vintage"],
    }

    if spatial_status == "UNAVAILABLE":
        base.update({
            "mean_m": None, "min_m": None, "max_m": None,
            "range_m": None, "std_m": None, "sample_count": None,
            "note": (
                "No spatial-proxy geometry is available for this GP "
                f"(missing constituent villages: {gp['missing_villages']}). "
                "DEM sampling was not attempted -- elevation is not "
                "estimated or inferred from neighboring GPs."
            ),
        })
        return base

    stats = compute_zonal_stats(gp["geometry"], mosaic_array, transform, nodata=DEM_NODATA)
    _validate_stats(gp["panchayat_name"], stats)
    base.update(stats)
    if spatial_status == "PARTIAL":
        base["note"] = (
            f"PARTIAL coverage: sampled only from the {gp['matched_village_count']}/"
            f"{gp['expected_village_count']} constituent-village geometry actually "
            f"present in the spatial proxy (missing: {gp['missing_villages']}). "
            "These statistics describe only the covered area, not the full GP."
        )
    else:
        base["note"] = "COMPLETE coverage: all constituent villages present in the spatial proxy."
    return base


def build() -> dict:
    layer = load_spatial_proxy()  # read-only; never modified
    panchayats = layer["panchayats"]

    available_geoms = [gp["geometry"] for gp in panchayats if gp["geometry"] is not None]
    if not available_geoms:
        raise RuntimeError("STOP: spatial proxy has zero available geometries -- nothing to sample.")

    bbox = _union_bbox([_bbox_of_geometry(g) for g in available_geoms])
    tile_paths = fetch_tiles_for_bbox(*bbox)
    mosaic_array, transform, dem_crs = load_mosaic(tile_paths)
    if str(dem_crs).upper() not in ("EPSG:4326", "OGC:CRS84"):
        raise RuntimeError(f"STOP: DEM tiles are not WGS84 as expected (got {dem_crs}) -- do not silently reproject.")

    gp_records = [build_gp_elevation_record(gp, mosaic_array, transform) for gp in panchayats]
    gp_records.sort(key=lambda r: r["gp_name"])

    n_complete = sum(1 for r in gp_records if r["coverage_status"] == "COMPLETE")
    n_partial = sum(1 for r in gp_records if r["coverage_status"] == "PARTIAL")
    n_unavailable = sum(1 for r in gp_records if r["coverage_status"] == "UNAVAILABLE")

    expected = (10, 1, 1)
    actual = (n_complete, n_partial, n_unavailable)
    if actual != expected:
        raise RuntimeError(
            f"STOP: elevation coverage_status tally diverged from the spatial "
            f"proxy's own coverage (expected COMPLETE/PARTIAL/UNAVAILABLE="
            f"{expected}, got {actual}). The spatial proxy is the source of "
            f"truth here and must not have changed -- do not silently adapt."
        )

    output = {
        "type": "YelandurElevationContextLayer",
        "dataset_label": "Yelandur elevation context (Copernicus DEM GLO-30 zonal statistics)",
        "source": DEM_SOURCE,
        "source_type": DEM_SOURCE_TYPE,
        "vintage": DEM_VINTAGE,
        "resolution_m": DEM_RESOLUTION_M,
        "horizontal_crs": DEM_HORIZONTAL_CRS,
        "vertical_unit": DEM_VERTICAL_UNIT,
        "methodology": METHODOLOGY,
        "terminology_note": TERMINOLOGY_NOTE,
        "source_provenance": {
            "registry_url": REGISTRY_URL,
            "bucket": "s3://copernicus-dem-30m (region eu-central-1, public read, no-sign-request)",
            "documentation_url": "https://copernicus-dem-30m.s3.amazonaws.com/readme.html",
            "license_url": LICENSE_URL,
            "license_note": _license_note(),
            "tiles_used": sorted({p.stem for p in tile_paths}),
            "spatial_proxy_input": "research/spatial_proxy/yelandur_spatial_proxy.json (read-only; not modified)",
        },
        "coverage_summary": {
            "expected_gp_count": 12,
            "complete_gp_count": n_complete,
            "partial_gp_count": n_partial,
            "unavailable_gp_count": n_unavailable,
        },
        "panchayats": gp_records,
    }
    return output


if __name__ == "__main__":
    result = build()
    OUTPUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    print(f"Coverage: {result['coverage_summary']}")
