"""
Small-pilot ERA5-Land acquisition.

Downloads ONE small bounding box (covering the pilot block + 3 demo
panchayats already defined in backend/app/geospatial/seed_data.py) for a
SHORT, hardcoded-small date range. This deliberately does NOT download
years of data  -  widen PILOT_DAYS/PILOT_YEAR only after the small request
below is proven to work end-to-end.

This module makes a REAL network request to the Copernicus Climate Data
Store when run. It does not simulate, cache, or fabricate a response  -  if
credentials are missing or the request fails, it raises, it does not
pretend to succeed.

Prerequisites (see research/README.md for the full walkthrough):
  1. A free CDS account, with the Terms of Use for "ERA5-Land hourly data"
     accepted from its dataset page (this step MUST be done manually in a
     browser  -  there is no API for accepting terms).
  2. CDSAPI_KEY (and optionally CDSAPI_URL) set as environment variables,
     or a ~/.cdsapirc file  -  see config.py.
"""

from pathlib import Path

from config import get_cds_client
from era5_land.archive import ensure_netcdf

DATASET = "reanalysis-era5-land"

VARIABLES = [
    "2m_temperature",
    "2m_dewpoint_temperature",
    "total_precipitation",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
]

# Deliberately small: 3 days of hourly data, one month, one year.
PILOT_YEAR = "2023"
PILOT_MONTH = "06"
PILOT_DAYS = ["01", "02", "03"]
PILOT_TIMES = [f"{h:02d}:00" for h in range(24)]

# Bounding box [North, West, South, East] covering the pilot block centroid
# (13.40 N, 77.73 E) and all 3 demo panchayats (13.37-13.50 N, 77.50-77.90 E)
# with a small pad. This is intentionally a tiny area, not a whole state.
PILOT_AREA = [13.55, 77.45, 13.30, 77.95]

RAW_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "era5_land"


def build_pilot_request() -> dict:
    """The exact request dict sent to CDS  -  separated out so it can be
    inspected/tested without needing real credentials or network access."""
    return {
        "variable": VARIABLES,
        "year": [PILOT_YEAR],
        "month": [PILOT_MONTH],
        "day": PILOT_DAYS,
        "time": PILOT_TIMES,
        "area": PILOT_AREA,
        "data_format": "netcdf",
    }


def download_pilot(output_path: Path | None = None) -> Path:
    """
    Submits the small pilot request and blocks until CDS has prepared and
    served the file. Raises on any failure (missing credentials, network
    error, CDS queueing/processing error)  -  never returns a path to a file
    that wasn't actually, successfully downloaded.
    """
    client = get_cds_client()  # raises MissingCredentialsError if unconfigured

    output_path = output_path or (RAW_OUTPUT_DIR / f"era5_land_pilot_{PILOT_YEAR}{PILOT_MONTH}.nc")
    RAW_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    client.retrieve(DATASET, build_pilot_request(), str(output_path))

    # CDS has been observed to deliver "data_format": "netcdf" requests as a
    # ZIP archive containing the actual .nc file, despite the output path
    # ending in .nc - detect and correct that here. No-op if the response
    # is already a bare NetCDF file.
    return ensure_netcdf(output_path)


if __name__ == "__main__":
    downloaded_path = download_pilot()
    print(f"Downloaded: {downloaded_path}")
