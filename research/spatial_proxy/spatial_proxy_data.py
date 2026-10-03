"""
Loader/validator for the committed Yelandur historical village-union
spatial proxy layer (yelandur_spatial_proxy.json, produced by build.py from
the real LGD + DataMeet sources -- see README.md for full provenance).

IDENTITY + 1991-VINTAGE GEOMETRY ONLY. This layer is a "historical
village-union spatial proxy" / "1991-vintage spatial proxy derived from
village polygons" -- never a present-day administrative boundary. It is
deliberately unlinked from ERA5-Land and from any downscaling/training code
under research/pipeline/ -- do not add that linkage here.
"""

import json
from pathlib import Path

LAYER_PATH = Path(__file__).resolve().parent / "yelandur_spatial_proxy.json"

REQUIRED_GP_FIELDS = [
    "state_lgd_code", "district_lgd_code", "taluka_panchayat_lgd_code",
    "panchayat_lgd_code", "panchayat_name",
    "expected_village_count", "matched_village_count", "missing_village_count",
    "geometry_status", "geometry_source", "geometry_vintage", "geometry_basis",
    "source_license", "source_positional_error", "source_crs",
    "source_blob_sha", "source_content_commit", "source_note",
    "constituent_villages",
]

VALID_GEOMETRY_STATUSES = {"COMPLETE", "PARTIAL", "UNAVAILABLE"}


def load_layer(path: Path = LAYER_PATH) -> dict:
    """Loads and lightly validates the committed layer. Raises if a GP
    record is missing a required field or has an unrecognized
    geometry_status -- this dataset exists specifically to guarantee a
    complete, self-describing provenance trail."""
    with open(path, encoding="utf-8") as f:
        layer = json.load(f)

    panchayats = layer.get("panchayats")
    if not panchayats:
        raise ValueError(f"{path} contains no panchayat records.")

    for i, gp in enumerate(panchayats):
        missing = [field for field in REQUIRED_GP_FIELDS if field not in gp]
        if missing:
            raise ValueError(f"GP record {i} in {path} is missing required field(s): {missing}")
        if gp["geometry_status"] not in VALID_GEOMETRY_STATUSES:
            raise ValueError(f"GP record {i} has invalid geometry_status: {gp['geometry_status']}")
        if gp["geometry_status"] == "UNAVAILABLE" and gp.get("geometry") is not None:
            raise ValueError(f"GP '{gp['panchayat_name']}' is UNAVAILABLE but has a stored geometry.")
        if gp["geometry_status"] != "UNAVAILABLE" and gp.get("geometry") is None:
            raise ValueError(f"GP '{gp['panchayat_name']}' is {gp['geometry_status']} but has no stored geometry.")

    return layer


def get_panchayats(layer: dict | None = None) -> list[dict]:
    layer = layer if layer is not None else load_layer()
    return layer["panchayats"]


def get_panchayat(gp_name: str, layer: dict | None = None) -> dict:
    for gp in get_panchayats(layer):
        if gp["panchayat_name"] == gp_name:
            return gp
    raise KeyError(f"No panchayat named '{gp_name}' in the spatial proxy layer.")
