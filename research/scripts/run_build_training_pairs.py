"""
Phase 2A step: normalized per-point CSVs -> training-pair dataset.

Usage:
    python research/scripts/run_build_training_pairs.py

Requires the CSVs produced by run_normalize.py to already exist. Does not
fabricate rows if they don't  -  stops and says so.
"""

import sys
from pathlib import Path

import pandas as pd

RESEARCH_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH_DIR))

from pilot_points import RESEARCH_BLOCK, RESEARCH_PANCHAYATS  # noqa: E402
from pipeline.training_pairs import build_training_pairs  # noqa: E402

PROCESSED_DIR = RESEARCH_DIR.parent / "data" / "processed" / "weather"
TRAINING_DIR = RESEARCH_DIR.parent / "data" / "training"


def _load(point_id: str) -> pd.DataFrame | None:
    path = PROCESSED_DIR / f"{point_id}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["timestamp"])
    return df


def main() -> int:
    coarse_df = _load(RESEARCH_BLOCK["block_id"])
    if coarse_df is None:
        print(f"BLOCKED  -  no normalized block data at {PROCESSED_DIR / (RESEARCH_BLOCK['block_id'] + '.csv')}")
        print("Run run_pilot_acquisition.py then run_normalize.py first.")
        return 1

    fine_by_panchayat = {}
    panchayats = []
    for p in RESEARCH_PANCHAYATS:
        df = _load(p["panchayat_id"])
        if df is None:
            print(f"  (skipping {p['panchayat_id']}: no normalized data found)")
            continue
        fine_by_panchayat[p["panchayat_id"]] = df
        panchayats.append({
            "panchayat_id": p["panchayat_id"], "block_id": p["block_id"],
            "latitude": p["latitude"], "longitude": p["longitude"],
            "elevation_m": p["elevation_m"], "landcover_class": None,  # not yet acquired  -  see Phase 1.5 report
        })

    if not panchayats:
        print("BLOCKED  -  no panchayat normalized data available at all.")
        return 1

    block = {"block_id": RESEARCH_BLOCK["block_id"], "latitude": RESEARCH_BLOCK["latitude"],
             "longitude": RESEARCH_BLOCK["longitude"], "elevation_m": RESEARCH_BLOCK["elevation_m"]}

    pairs = build_training_pairs(coarse_df, fine_by_panchayat, panchayats, block)

    TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    out_path = TRAINING_DIR / "training_pairs.csv"
    pairs.to_csv(out_path, index=False)

    print(f"Training pairs written: {len(pairs)} rows -> {out_path}")
    if pairs.empty:
        print("WARNING: 0 rows. Coarse and fine data did not share any (timestamp, variable)  -  "
              "check that both were normalized from overlapping time ranges.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
