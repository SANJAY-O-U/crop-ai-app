"""
Stage 4C acquisition: land/sea validation, GLO-30 tiles, and 2021-2023
ERA5 + ERA5-Land for the 11 frozen Stage 4 areas.

Reuses, never modifies: config.get_cds_client (the one auth path),
era5_land.archive.ensure_netcdf (ZIP handling), multi_gp.acquire (window,
variables, hours, monthly file conventions), elevation.acquire.fetch_tile.

Request batching: ONE combined area per product per month (72 requests),
the union of the frozen per-area request boxes. CDS queue cost is per
request (fields = variables x hours; area does not change it), so this
trades ~1.5 GB of extra grid points for 72 instead of 792 requests.

Every CDS download writes a sidecar "<file>.request.json" with the CDS job
id, result URL, product, exact request and response size.
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from config import get_cds_client  # noqa: E402
from era5_land.archive import ensure_netcdf  # noqa: E402
from multi_gp import acquire as p2d  # noqa: E402

REPO = _RESEARCH_DIR.parent
DESIGN_MANIFEST = Path(__file__).resolve().parent / "stage4_acquisition_manifest.json"
LAND_DIR = REPO / "data" / "raw" / "era5_land" / "stage4"
ERA5_DIR = REPO / "data" / "raw" / "era5" / "stage4"
LAND_SEA_PROBE = LAND_DIR / "land_sea_probe_2023010100.nc"
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def load_design() -> dict:
    return json.loads(DESIGN_MANIFEST.read_text(encoding="utf-8"))


def union_area(areas: list[list[float]]) -> list[float]:
    return [max(a[0] for a in areas), min(a[1] for a in areas), min(a[2] for a in areas), max(a[3] for a in areas)]


def combined_areas(design: dict) -> dict:
    sel = design["selected"]
    return {"era5_land": union_area([e["era5_land_request_area_nwse"] for e in sel]),
            "era5": union_area([e["era5_request_area_nwse"] for e in sel])}


def era5_land_path(year: int, month: int) -> Path:
    return LAND_DIR / f"era5_land_stage4_{year}{month:02d}.nc"


def era5_path(year: int, month: int) -> Path:
    return ERA5_DIR / f"era5_stage4_{year}{month:02d}.nc"


def sidecar(path: Path) -> Path:
    return path.with_name(path.name + ".request.json")


def land_request(year: int, month: int, area: list[float]) -> dict:
    return {**p2d.build_era5_land_request(year, month), "area": list(area)}


def era5_request(year: int, month: int, area: list[float]) -> dict:
    return {**p2d.build_era5_request(year, month), "area": list(area)}


def download(dataset: str, request: dict, path: Path) -> Path:
    """Idempotent: an existing primary file means the request completed."""
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    result = get_cds_client().retrieve(dataset, request)  # no target -> Results with job metadata
    tmp = path.with_name(path.stem + ".part.nc")
    result.download(str(tmp))
    ensure_netcdf(tmp)
    for extra in sorted(tmp.parent.glob(f"{tmp.stem}__*.nc")):
        extra.replace(path.parent / extra.name.replace(tmp.stem, path.stem, 1))
    zip_copy = tmp.with_suffix(".zip")
    if zip_copy.exists():
        zip_copy.replace(path.with_suffix(".zip"))
    url = getattr(result, "url", None) or getattr(result, "location", None)
    match = _UUID.search(str(url or ""))
    sidecar(path).write_text(json.dumps({
        "request_id": match.group(0) if match else None,
        "result_url": url,
        "content_length_bytes": getattr(result, "content_length", None),
        "dataset": dataset,
        "request": request,
        "downloaded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, indent=2), encoding="utf-8")
    tmp.replace(path)  # primary last: its presence marks the request complete
    return path


def land_sea_probe(design: dict) -> Path:
    req = design["land_sea_4a"]["required_acquisition"]
    return download(req["dataset"], req["request"], LAND_SEA_PROBE)


def fetch_elevation_tiles(design: dict) -> list[Path]:
    from elevation.acquire import fetch_public_tile_list, fetch_tile

    public = fetch_public_tile_list()
    keys = sorted({t.replace("Copernicus_DSM_COG_10_", "").replace("_DEM", "")
                   for e in design["selected"] for t in e["elevation"]["glo30_tiles_required"]})
    return [fetch_tile(k, public) for k in keys]


def weather_jobs(design: dict) -> list[tuple[str, dict, Path]]:
    areas = combined_areas(design)
    jobs = []
    for y, m in p2d.window_months():
        jobs.append((p2d.ERA5_LAND_DATASET, land_request(y, m, areas["era5_land"]), era5_land_path(y, m)))
        jobs.append((p2d.ERA5_DATASET, era5_request(y, m, areas["era5"]), era5_path(y, m)))
    return jobs


def acquire_weather(design: dict, max_workers: int = 4) -> None:
    jobs = [j for j in weather_jobs(design) if not j[2].exists()]
    print(f"{len(jobs)} monthly request(s) outstanding", flush=True)
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(download, *j): j for j in jobs}
        for fut in as_completed(futures):
            done += 1
            print(f"  done: {fut.result().name} ({done}/{len(jobs)})", flush=True)


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    d = load_design()
    if step in ("probe", "all"):
        print("land/sea probe:", land_sea_probe(d))
    if step in ("tiles", "all"):
        print("tiles:", [p.name for p in fetch_elevation_tiles(d)])
    if step in ("weather", "all"):
        acquire_weather(d)
