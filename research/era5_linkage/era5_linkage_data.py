"""
Loader/validator for the committed Yelandur ERA5-Land spatial-linkage layer
(yelandur_era5_linkage.json, produced by build.py -- see README.md).

SPATIAL LINKAGE ONLY. This is not downscaling and not a forecast. ERA5-Land
values referenced here are reanalysis data, never observations. Deliberately
unlinked from any model-training code -- do not add that linkage here.
"""

import json
from pathlib import Path

LAYER_PATH = Path(__file__).resolve().parent / "yelandur_era5_linkage.json"

REQUIRED_GP_FIELDS = [
    "panchayat_lgd_code", "gp_name", "coverage_status",
    "centroid_latitude", "centroid_longitude",
    "nearest_grid_latitude", "nearest_grid_longitude",
    "latitude_difference_deg", "longitude_difference_deg",
    "centroid_to_grid_distance_km",
    "intersecting_cell_count", "intersecting_cells", "linkage_status",
]

VALID_COVERAGE_STATUSES = {"COMPLETE", "PARTIAL", "UNAVAILABLE"}
VALID_LINKAGE_STATUSES = {
    "SINGLE_CELL", "MULTI_CELL", "NO_INTERSECTION",
    "BLOCKED_NO_ERA5_GRID_DATA", "UNAVAILABLE",
}


def load_layer(path: Path = LAYER_PATH) -> dict:
    """Loads and lightly validates the committed layer. Raises if a GP
    record is missing a required field, has an unrecognized status, or has
    a numeric-vs-null contradiction (e.g. UNAVAILABLE with a non-null
    centroid)."""
    with open(path, encoding="utf-8") as f:
        layer = json.loads(f.read())

    panchayats = layer.get("panchayats")
    if not panchayats:
        raise ValueError(f"{path} contains no panchayat records.")

    for i, gp in enumerate(panchayats):
        missing = [field for field in REQUIRED_GP_FIELDS if field not in gp]
        if missing:
            raise ValueError(f"GP record {i} in {path} is missing required field(s): {missing}")
        if gp["coverage_status"] not in VALID_COVERAGE_STATUSES:
            raise ValueError(f"GP record {i} has invalid coverage_status: {gp['coverage_status']}")
        if gp["linkage_status"] not in VALID_LINKAGE_STATUSES:
            raise ValueError(f"GP record {i} has invalid linkage_status: {gp['linkage_status']}")
        if gp["coverage_status"] == "UNAVAILABLE":
            for field in ("centroid_latitude", "centroid_longitude", "nearest_grid_latitude",
                           "nearest_grid_longitude", "centroid_to_grid_distance_km", "intersecting_cell_count"):
                if gp[field] is not None:
                    raise ValueError(f"GP '{gp['gp_name']}' is UNAVAILABLE but has non-null {field}={gp[field]}")

    return layer


def get_panchayats(layer: dict | None = None) -> list[dict]:
    layer = layer if layer is not None else load_layer()
    return layer["panchayats"]


def get_panchayat(gp_name: str, layer: dict | None = None) -> dict:
    for gp in get_panchayats(layer):
        if gp["gp_name"] == gp_name:
            return gp
    raise KeyError(f"No panchayat named '{gp_name}' in the ERA5-Land linkage layer.")
