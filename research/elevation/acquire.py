"""
Reproducible fetch of Copernicus DEM GLO-30 tiles covering the Yelandur
spatial proxy geometries.

OFFICIAL ACCESS MECHANISM -- inspected this session, not invented:

  Registry of Open Data on AWS entry:
    https://registry.opendata.aws/copernicus-dem/
  S3 bucket (public read, "--no-sign-request", no AWS account needed):
    s3://copernicus-dem-30m/   (region eu-central-1)
  Bucket-provided documentation:
    https://copernicus-dem-30m.s3.amazonaws.com/readme.html
  Managed by Sinergise on behalf of the Copernicus Programme. License:
    https://dataspace.copernicus.eu/explore-data/data-collections/
    copernicus-contributing-missions/collections-description/COP-DEM

This module downloads tiles over plain HTTPS from that bucket's
virtual-hosted-style public URLs (verified this session with `curl -I`:
200 OK, no auth headers required, Accept-Ranges: bytes). No AWS
credentials, no Copernicus Data Space Ecosystem registration, and no
undocumented endpoint are used anywhere here.

Tile naming (per the bucket's own readme.html, "Data structure" section):

  Copernicus_DSM_COG_10_{northing}_00_{easting}_00_DEM/
      Copernicus_DSM_COG_10_{northing}_00_{easting}_00_DEM.tif

  resolution "10" = 10 arc-seconds = GLO-30 (nominal ~30m).
  {northing} e.g. "N11" / "S50" -- 2-digit degrees, southwest-corner origin.
  {easting}  e.g. "E077" / "W125" -- 3-digit degrees, southwest-corner origin.

GLO-30 Public does NOT cover every country yet -- the bucket publishes its
own authoritative `tileList.txt` of what's actually public. This module
checks every required tile against that list before attempting a download,
and raises a clear, actionable error (never a silent substitution) if a
required tile isn't public.
"""

import math
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "elevation"

BUCKET_BASE_URL = "https://copernicus-dem-30m.s3.amazonaws.com"
TILE_LIST_URL = f"{BUCKET_BASE_URL}/tileList.txt"
RESOLUTION_CODE = "10"  # arc-seconds; GLO-30

REGISTRY_URL = "https://registry.opendata.aws/copernicus-dem/"
LICENSE_URL = (
    "https://dataspace.copernicus.eu/explore-data/data-collections/"
    "copernicus-contributing-missions/collections-description/COP-DEM"
)


class DemAcquisitionBlocked(RuntimeError):
    """Raised when a required tile is not available via the public GLO-30
    mechanism. Callers must not catch this and silently fall back to a
    different DEM or fabricate elevation data."""


def tile_key(lat_deg: float, lon_deg: float) -> str:
    """Returns the Copernicus DEM tile-name fragment (e.g. "N11_00_E077_00")
    for the 1x1-degree tile whose southwest corner is the integer floor of
    (lat_deg, lon_deg), per the bucket's own naming convention."""
    lat_floor = math.floor(lat_deg)
    lon_floor = math.floor(lon_deg)
    ns = "N" if lat_floor >= 0 else "S"
    ew = "E" if lon_floor >= 0 else "W"
    return f"{ns}{abs(lat_floor):02d}_00_{ew}{abs(lon_floor):03d}_00"


def tiles_covering_bbox(minx: float, miny: float, maxx: float, maxy: float) -> list[str]:
    """All 1x1-degree tile keys whose tiles intersect the given WGS84
    bounding box (minx=min lon, miny=min lat, maxx=max lon, maxy=max lat)."""
    lat_start, lat_end = math.floor(miny), math.floor(maxy)
    lon_start, lon_end = math.floor(minx), math.floor(maxx)
    keys = []
    for lat_floor in range(lat_start, lat_end + 1):
        for lon_floor in range(lon_start, lon_end + 1):
            keys.append(tile_key(lat_floor, lon_floor))
    return keys


def _tile_dir_name(tile: str) -> str:
    return f"Copernicus_DSM_COG_{RESOLUTION_CODE}_{tile}_DEM"


def _tile_url(tile: str) -> str:
    name = _tile_dir_name(tile)
    return f"{BUCKET_BASE_URL}/{name}/{name}.tif"


def fetch_public_tile_list() -> set[str]:
    """Downloads (or reuses a local cache of) the bucket's own
    authoritative list of publicly-released GLO-30 tile directory names."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = RAW_DIR / "tileList.txt"
    if not cache_path.exists():
        with urllib.request.urlopen(TILE_LIST_URL, timeout=60) as resp:
            cache_path.write_bytes(resp.read())
    names = {
        line.strip() for line in cache_path.read_text(encoding="utf-8").splitlines() if line.strip()
    }
    return names


def fetch_tile(tile: str, public_tile_names: set[str]) -> Path:
    """Downloads one DEM tile's Cloud-Optimized GeoTIFF into
    data/raw/elevation/ (gitignored). Raises DemAcquisitionBlocked if the
    tile is not in GLO-30 Public's own tile list -- this is the documented
    "STOP, don't substitute" case, not a fabricated fallback."""
    dir_name = _tile_dir_name(tile)
    if dir_name not in public_tile_names:
        raise DemAcquisitionBlocked(
            f"Copernicus DEM GLO-30 tile '{dir_name}' is not present in the "
            f"public tile list ({TILE_LIST_URL}). GLO-30 Public excludes a "
            f"small set of countries not yet released by the Copernicus "
            f"Programme. Refusing to substitute GLO-90 or any other DEM -- "
            f"see README.md 'Acquisition blocker' section."
        )

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    tif_path = RAW_DIR / f"{dir_name}.tif"
    if not tif_path.exists():
        with urllib.request.urlopen(_tile_url(tile), timeout=180) as resp:
            tif_path.write_bytes(resp.read())
    return tif_path


def fetch_tiles_for_bbox(minx: float, miny: float, maxx: float, maxy: float) -> list[Path]:
    """Fetches every GLO-30 tile intersecting the given WGS84 bounding box.
    Idempotent -- already-cached tiles are not re-downloaded."""
    public_names = fetch_public_tile_list()
    tiles = tiles_covering_bbox(minx, miny, maxx, maxy)
    return [fetch_tile(t, public_names) for t in tiles]


if __name__ == "__main__":
    # Yelandur taluk's actual bbox (see build.py, which computes this
    # precisely from the real spatial-proxy geometries -- some GP polygons
    # dip slightly west of 77.0E, so both E076 and E077 tiles are needed).
    # Given here only so this module is independently runnable for
    # standalone cache-warming.
    paths = fetch_tiles_for_bbox(minx=76.99, miny=11.95, maxx=77.19, maxy=12.15)
    for p in paths:
        print(f"cached: {p}")
