"""
Loader for the Stage 1 real Karnataka Panchayat identity dataset
(karnataka_identity.csv, produced by fetch_lgd_identity.py from the actual
LGD mirror — see that script's docstring and README.md for full
provenance).

IDENTITY/METADATA ONLY. Deliberately has no coordinate/elevation/geometry
fields and no relationship to research/pilot_points.py, ERA5-Land, or any
grid cell. Do not add spatial fields to this module — that is a separate,
not-yet-approved stage.
"""

import csv
from pathlib import Path

IDENTITY_CSV_PATH = Path(__file__).resolve().parent / "karnataka_identity.csv"

REQUIRED_FIELDS = [
    "state_name", "state_lgd_code",
    "district_name", "district_lgd_code",
    "block_name", "block_lgd_code",
    "panchayat_name", "panchayat_lgd_code",
    "source", "source_url", "retrieved_at", "source_note",
]


def load_identity_rows(path: Path = IDENTITY_CSV_PATH) -> list[dict]:
    """Loads and lightly validates the committed identity dataset. Raises
    if a row is missing a required field or has an empty LGD code — this
    dataset exists specifically to guarantee real, present codes."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError(f"{path} contains no rows.")

    for i, row in enumerate(rows):
        missing = [field for field in REQUIRED_FIELDS if not row.get(field)]
        if missing:
            raise ValueError(f"Row {i} in {path} is missing required field(s): {missing}")

    return rows


def get_block_summary(rows: list[dict] | None = None) -> dict:
    """The single block these panchayats belong to, as one summary dict.
    Raises if the loaded rows somehow span more than one block — this
    dataset is defined to be exactly one block's panchayats."""
    rows = rows if rows is not None else load_identity_rows()
    block_codes = {r["block_lgd_code"] for r in rows}
    if len(block_codes) != 1:
        raise ValueError(f"Expected exactly one block, found block_lgd_codes: {block_codes}")

    first = rows[0]
    return {
        "state_name": first["state_name"],
        "state_lgd_code": first["state_lgd_code"],
        "district_name": first["district_name"],
        "district_lgd_code": first["district_lgd_code"],
        "block_name": first["block_name"],
        "block_lgd_code": first["block_lgd_code"],
    }
