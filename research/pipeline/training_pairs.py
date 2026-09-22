"""
coarse (block) -> fine (panchayat) training-pair construction.

One output row = one trainable example: a single variable, at a single
timestamp, for a single panchayat, with the block's (coarse) value, the
panchayat's (fine, proxy) target value, and the static covariates needed to
eventually fit a correction model (elevation delta, land cover if available).

Every row's `source_note` is explicitly "reanalysis proxy — not observation"
per the CRITICAL instruction never to call this real ground truth.
"""

import pandas as pd

TRAINING_PAIR_COLUMNS = [
    "timestamp", "block_id", "panchayat_id", "variable",
    "coarse_value", "coarse_unit",
    "fine_value", "fine_unit",
    "block_elevation_m", "panchayat_elevation_m", "elevation_delta_m",
    "landcover_class",
    "block_latitude", "block_longitude",
    "panchayat_latitude", "panchayat_longitude",
    "source_note",
]

SOURCE_NOTE = "reanalysis proxy — not observation"


def build_training_pairs(
    coarse_df: pd.DataFrame,
    fine_by_panchayat: dict[str, pd.DataFrame],
    panchayats: list[dict],
    block: dict,
) -> pd.DataFrame:
    """
    coarse_df: long-format normalize.py output for the BLOCK point
               (timestamp, latitude, longitude, variable, value, unit, source)
    fine_by_panchayat: {panchayat_id: long-format DataFrame for that panchayat}
    panchayats: [{panchayat_id, block_id, latitude, longitude, elevation_m,
                  landcover_class (optional)}, ...]
    block: {block_id, latitude, longitude, elevation_m}
    """
    if coarse_df.empty:
        return pd.DataFrame(columns=TRAINING_PAIR_COLUMNS)

    coarse = coarse_df.rename(columns={"value": "coarse_value", "unit": "coarse_unit"})
    coarse = coarse[["timestamp", "variable", "coarse_value", "coarse_unit"]]

    all_rows = []
    for panchayat in panchayats:
        pid = panchayat["panchayat_id"]
        fine_df = fine_by_panchayat.get(pid)
        if fine_df is None or fine_df.empty:
            continue

        fine = fine_df.rename(columns={"value": "fine_value", "unit": "fine_unit"})
        fine = fine[["timestamp", "variable", "fine_value", "fine_unit"]]

        merged = pd.merge(coarse, fine, on=["timestamp", "variable"], how="inner")
        if merged.empty:
            continue

        elevation_delta = None
        if panchayat.get("elevation_m") is not None and block.get("elevation_m") is not None:
            elevation_delta = panchayat["elevation_m"] - block["elevation_m"]

        merged["block_id"] = panchayat.get("block_id", block.get("block_id"))
        merged["panchayat_id"] = pid
        merged["block_elevation_m"] = block.get("elevation_m")
        merged["panchayat_elevation_m"] = panchayat.get("elevation_m")
        merged["elevation_delta_m"] = elevation_delta
        merged["landcover_class"] = panchayat.get("landcover_class")
        merged["block_latitude"] = block.get("latitude")
        merged["block_longitude"] = block.get("longitude")
        merged["panchayat_latitude"] = panchayat.get("latitude")
        merged["panchayat_longitude"] = panchayat.get("longitude")
        merged["source_note"] = SOURCE_NOTE

        all_rows.append(merged)

    if not all_rows:
        return pd.DataFrame(columns=TRAINING_PAIR_COLUMNS)

    result = pd.concat(all_rows, ignore_index=True)
    return result[TRAINING_PAIR_COLUMNS]
