"""
Stage 5 acquisition: ISD global-hourly 2023 files for the matched stations
(PRIMARY + NEARBY_DIAGNOSTIC from station_matching.csv), plus the station
history file. Raw files live in data/raw/observations/ (gitignored).
Idempotent; every file's URL, size and SHA-256 go to results/provenance.json.
"""

import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

REPO = _RESEARCH_DIR.parent
MODULE = Path(__file__).resolve().parent
RESULTS = MODULE / "results"
RAW = REPO / "data" / "raw" / "observations" / "isd"
HISTORY_URL = "https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv"
HOURLY_URL = "https://www.ncei.noaa.gov/data/global-hourly/access/{year}/{sid}.csv"
YEAR = 2023


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def station_file(station_id: str, year: int = YEAR) -> Path:
    return RAW / "global-hourly" / str(year) / f"{station_id.replace('-', '')}.csv"


def _fetch(url: str, path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=180) as resp:
        path.write_bytes(resp.read())


def _record(url: str, path: Path) -> dict:
    return {"url": url, "file": path.relative_to(REPO).as_posix(), "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "retrieved_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")}


def run() -> dict:
    matching = pd.read_csv(RESULTS / "station_matching.csv", dtype={"station_id": str})
    stations = matching[matching["match_set"] != "EXCLUDED"]
    hist = RAW / "isd-history.csv"
    _fetch(HISTORY_URL, hist)
    files = {"station_history": _record(HISTORY_URL, hist)}
    for sid in stations["station_id"]:
        url = HOURLY_URL.format(year=YEAR, sid=sid.replace("-", ""))
        path = station_file(sid)
        _fetch(url, path)
        files[sid] = _record(url, path)
    return files


if __name__ == "__main__":
    print(json.dumps(run(), indent=1))
