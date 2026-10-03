"""
Loader/validator for the committed Yelandur elevation-context layer
(yelandur_elevation.json, produced by build.py -- see README.md for full
methodology and provenance).

CONTEXTUAL ELEVATION ONLY. Deliberately unlinked from ERA5-Land and from
research/pipeline/training_pairs.py -- do not add that linkage here.
"""

import json
from pathlib import Path

LAYER_PATH = Path(__file__).resolve().parent / "yelandur_elevation.json"

REQUIRED_GP_FIELDS = [
    "gp_id", "gp_name", "coverage_status", "source", "resolution_m",
    "mean_m", "min_m", "max_m", "range_m", "std_m", "sample_count",
    "methodology",
]

VALID_COVERAGE_STATUSES = {"COMPLETE", "PARTIAL", "UNAVAILABLE"}


def load_layer(path: Path = LAYER_PATH) -> dict:
    """Loads and lightly validates the committed layer. Raises if a GP
    record is missing a required field, has an unrecognized
    coverage_status, or has a numeric-vs-null contradiction (e.g. an
    UNAVAILABLE GP carrying a non-null mean_m)."""
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
        if gp["coverage_status"] == "UNAVAILABLE":
            for field in ("mean_m", "min_m", "max_m", "range_m", "std_m", "sample_count"):
                if gp[field] is not None:
                    raise ValueError(f"GP '{gp['gp_name']}' is UNAVAILABLE but has non-null {field}={gp[field]}")
        else:
            for field in ("mean_m", "min_m", "max_m", "range_m", "std_m", "sample_count"):
                if gp[field] is None:
                    raise ValueError(f"GP '{gp['gp_name']}' is {gp['coverage_status']} but has null {field}")

    return layer


def get_panchayats(layer: dict | None = None) -> list[dict]:
    layer = layer if layer is not None else load_layer()
    return layer["panchayats"]


def get_panchayat(gp_name: str, layer: dict | None = None) -> dict:
    for gp in get_panchayats(layer):
        if gp["gp_name"] == gp_name:
            return gp
    raise KeyError(f"No panchayat named '{gp_name}' in the elevation layer.")
