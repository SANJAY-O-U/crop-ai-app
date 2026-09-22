"""
Phase 2A step: raw ERA5-Land netCDF -> normalized per-point CSVs.

Usage:
    python research/scripts/run_normalize.py [path/to/file.nc]

If no path is given, uses the default pilot output path from
era5_land/acquire.py. Requires a real file produced by
run_pilot_acquisition.py  -  this script does not fabricate data if the file
is missing, it stops and says so.
"""

import sys
from pathlib import Path

RESEARCH_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH_DIR))

from era5_land.acquire import RAW_OUTPUT_DIR, PILOT_YEAR, PILOT_MONTH  # noqa: E402
from pilot_points import RESEARCH_BLOCK, RESEARCH_PANCHAYATS  # noqa: E402
from pipeline.normalize import normalize_era5_land_file  # noqa: E402

PROCESSED_DIR = RESEARCH_DIR.parent / "data" / "processed" / "weather"


def main() -> int:
    raw_path = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        RAW_OUTPUT_DIR / f"era5_land_pilot_{PILOT_YEAR}{PILOT_MONTH}.nc"
    )

    if not raw_path.exists():
        print(f"BLOCKED  -  raw file not found: {raw_path}")
        print("Run research/scripts/run_pilot_acquisition.py first.")
        return 1

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    points = [{"id": RESEARCH_BLOCK["block_id"], "role": "block",
               "lat": RESEARCH_BLOCK["latitude"], "lon": RESEARCH_BLOCK["longitude"]}]
    points += [{"id": p["panchayat_id"], "role": "panchayat", "lat": p["latitude"], "lon": p["longitude"]}
               for p in RESEARCH_PANCHAYATS]

    for point in points:
        df = normalize_era5_land_file(str(raw_path), point["lat"], point["lon"])
        out_path = PROCESSED_DIR / f"{point['id']}.csv"
        df.to_csv(out_path, index=False)
        print(f"{point['role']:>10} {point['id']:<18} -> {len(df):>5} rows -> {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
