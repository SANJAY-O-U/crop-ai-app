"""
Multi-year acquisition for the Phase 2D Yelandur multi-GP dataset.

ISOLATED from the Phase 2A pilot: era5_land/acquire.py (3 days, June 2023)
is imported for its dataset/variable constants only and is never modified.
Authentication is the ONE existing path, config.get_cds_client(); CDS ZIP
responses are handled by the existing era5_land.archive.ensure_netcdf().

Two products, both REANALYSIS (neither is a forecast):
  - "reanalysis-era5-land"          -- 0.1 deg ERA5-Land, the target/proxy
  - "reanalysis-era5-single-levels" -- 0.25 deg ERA5, the coarse input

One request per product per calendar month (small, retry-friendly requests;
each month is cached on disk and skipped if already present).

Verified against real CDS responses (2026-09-25):
  - ERA5 single-levels NetCDF arrives as a ZIP holding two members,
    "data_stream-oper_stepType-instant.nc" (t2m, d2m, u10, v10) and
    "data_stream-oper_stepType-accum.nc" (tp). ensure_netcdf() writes the
    first member at the requested path and any others alongside as
    "<stem>__<member>"; open_monthly() merges them back.
  - ERA5 grid: native 0.25 deg, latitude descending, longitude ascending.
  - ERA5 hourly `tp` is the accumulation over the hour ENDING at valid_time
    (non-monotonic within a day in real data) -- no de-accumulation needed,
    unlike ERA5-Land's since-00-UTC accumulation.
"""

import calendar
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from config import get_cds_client  # noqa: E402
from era5_land.acquire import DATASET as ERA5_LAND_DATASET  # noqa: E402
from era5_land.acquire import RAW_OUTPUT_DIR as ERA5_LAND_RAW_DIR  # noqa: E402
from era5_land.acquire import VARIABLES  # noqa: E402
from era5_land.archive import ensure_netcdf  # noqa: E402
from era5_linkage.build import YELANDUR_AREA  # noqa: E402

ERA5_DATASET = "reanalysis-era5-single-levels"

# Inclusive UTC window: three full calendar years = three complete
# monsoon/non-monsoon cycles. Contains (but does not reuse) the Phase 2A
# pilot's 2023-06-01..03 window.
WINDOW_START_YEAR = 2021
WINDOW_END_YEAR = 2023

# ERA5-Land target area: IDENTICAL to the Phase 2C linkage request, so every
# monthly file has exactly the grid the linkage artifact was computed on.
ERA5_LAND_AREA = YELANDUR_AREA

# ERA5 coarse area [N, W, S, E]: a 4x4 block of native 0.25 deg points. All
# ERA5-Land target cells (12.0-12.1N, 77.0-77.2E) lie inside the interior
# 2x2 block {12.0, 12.25} x {77.0, 77.25}, which is what bilinear pairing
# needs; the outer ring is context only.
ERA5_AREA = [12.5, 76.75, 11.75, 77.5]

RAW_ROOT = ERA5_LAND_RAW_DIR.parent  # data/raw
ERA5_LAND_MULTI_DIR = ERA5_LAND_RAW_DIR / "multi_gp"
ERA5_MULTI_DIR = RAW_ROOT / "era5" / "multi_gp"

HOURS = [f"{h:02d}:00" for h in range(24)]


def window_months(start_year: int = WINDOW_START_YEAR, end_year: int = WINDOW_END_YEAR) -> list[tuple[int, int]]:
    return [(y, m) for y in range(start_year, end_year + 1) for m in range(1, 13)]


def month_days(year: int, month: int) -> list[str]:
    return [f"{d:02d}" for d in range(1, calendar.monthrange(year, month)[1] + 1)]


def build_era5_land_request(year: int, month: int) -> dict:
    return {
        "variable": list(VARIABLES),
        "year": [str(year)],
        "month": [f"{month:02d}"],
        "day": month_days(year, month),
        "time": HOURS,
        "area": list(ERA5_LAND_AREA),
        "data_format": "netcdf",
    }


def build_era5_request(year: int, month: int) -> dict:
    return {
        "product_type": ["reanalysis"],
        "variable": list(VARIABLES),
        "year": [str(year)],
        "month": [f"{month:02d}"],
        "day": month_days(year, month),
        "time": HOURS,
        "area": list(ERA5_AREA),
        "data_format": "netcdf",
    }


def era5_land_path(year: int, month: int) -> Path:
    return ERA5_LAND_MULTI_DIR / f"era5_land_yelandur_{year}{month:02d}.nc"


def era5_path(year: int, month: int) -> Path:
    return ERA5_MULTI_DIR / f"era5_yelandur_{year}{month:02d}.nc"


def member_paths(path: Path) -> list[Path]:
    """The primary .nc plus any extra ZIP members ensure_netcdf() wrote
    alongside it, in a deterministic order."""
    extras = sorted(path.parent.glob(f"{path.stem}__*.nc"))
    return [path, *extras]


def open_monthly(path: Path):
    """Opens one monthly file, merging split ZIP members (ERA5's instant +
    accum streams) into one Dataset. Loads into memory and closes handles."""
    import xarray as xr

    parts = []
    for p in member_paths(path):
        with xr.open_dataset(p) as ds:
            parts.append(ds.load())
    return xr.merge(parts, compat="override", join="exact") if len(parts) > 1 else parts[0]


def _download(dataset: str, request: dict, path: Path) -> Path:
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".part.nc")
    get_cds_client().retrieve(dataset, request, str(tmp))
    # ensure_netcdf() unpacks a ZIP in place; extras land as "<tmp.stem>__*"
    ensure_netcdf(tmp)
    for extra in sorted(tmp.parent.glob(f"{tmp.stem}__*.nc")):
        extra.replace(path.parent / extra.name.replace(tmp.stem, path.stem, 1))
    zip_copy = tmp.with_suffix(".zip")
    if zip_copy.exists():
        zip_copy.replace(path.with_suffix(".zip"))
    tmp.replace(path)  # primary last: its presence marks the month complete
    return path


def acquisition_jobs() -> list[tuple[str, dict, Path]]:
    jobs = []
    for year, month in window_months():
        jobs.append((ERA5_LAND_DATASET, build_era5_land_request(year, month), era5_land_path(year, month)))
        jobs.append((ERA5_DATASET, build_era5_request(year, month), era5_path(year, month)))
    return jobs


def acquire_all(max_workers: int = 4) -> list[Path]:
    """Downloads every missing month for both products. Raises on the first
    real failure -- never writes a placeholder for a month that failed."""
    jobs = [j for j in acquisition_jobs() if not j[2].exists()]
    print(f"{len(jobs)} monthly request(s) outstanding")
    done = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_download, *job): job for job in jobs}
        for fut in as_completed(futures):
            done.append(fut.result())
            print(f"  done: {done[-1].name} ({len(done)}/{len(jobs)})", flush=True)
    return done


if __name__ == "__main__":
    acquire_all()
