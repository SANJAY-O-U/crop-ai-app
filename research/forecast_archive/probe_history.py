"""
One-off availability PROBE (research only): which historical forecast products does Open-Meteo expose for the pilot block
point? Each tiny request's raw response is saved under data/raw/open_meteo_history_probe/ and summarised in
results/history_probe.json. NO dataset is built from these responses in Phase 2C, and none of them is the production
`best_match` forecast as issued on a given day -- see PHASE2C_REPORT.md for the caveats.

    python research/forecast_archive/probe_history.py
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

_HERE = Path(__file__).resolve().parent
RAW = _HERE.parents[1] / "data" / "raw" / "open_meteo_history_probe"
LAT, LON = 13.40, 77.73          # live demo block point (backend/app/geospatial/seed_data.py)
BASE = {"latitude": LAT, "longitude": LON, "timezone": "auto"}
PROBES = {
    "forecast_live": ("https://api.open-meteo.com/v1/forecast", {"daily": "temperature_2m_min", "forecast_days": 2}),
    "historical_forecast_2022": ("https://historical-forecast-api.open-meteo.com/v1/forecast",
                                 {"daily": "temperature_2m_min", "start_date": "2022-06-01", "end_date": "2022-06-03"}),
    "historical_forecast_2023": ("https://historical-forecast-api.open-meteo.com/v1/forecast",
                                 {"daily": "temperature_2m_min", "start_date": "2023-06-01", "end_date": "2023-06-03"}),
    "previous_runs_2023": ("https://previous-runs-api.open-meteo.com/v1/forecast",
                           {"hourly": "temperature_2m,temperature_2m_previous_day1", "start_date": "2023-06-01", "end_date": "2023-06-01"}),
    "previous_runs_2025": ("https://previous-runs-api.open-meteo.com/v1/forecast",
                           {"hourly": "temperature_2m,temperature_2m_previous_day1,temperature_2m_previous_day3", "start_date": "2025-06-01", "end_date": "2025-06-01"}),
}


def main() -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    out = {"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "probes": {}}
    for name, (url, extra) in PROBES.items():
        params = {**BASE, **extra}
        try:
            r = httpx.get(url, params=params, timeout=20)
            (RAW / f"{name}.json").write_bytes(r.content)
            entry = {"url": url, "params": params, "http_status": r.status_code, "raw_sha256": hashlib.sha256(r.content).hexdigest()}
            if r.status_code == 200:
                block = r.json().get("daily") or r.json().get("hourly") or {}
                entry["variables"] = [k for k in block if k != "time"]
                entry["n_points"] = len(block.get("time", []))
                entry["non_null_counts"] = {k: sum(v is not None for v in block[k]) for k in entry["variables"]}
        except Exception as exc:  # noqa: BLE001
            entry = {"url": url, "params": params, "error": f"{type(exc).__name__}: {exc}"}
        out["probes"][name] = entry
    (_HERE / "results").mkdir(exist_ok=True)
    (_HERE / "results" / "history_probe.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({k: {kk: v.get(kk) for kk in ("http_status", "n_points", "non_null_counts", "error")} for k, v in out["probes"].items()}, indent=1))
    return out


if __name__ == "__main__":
    main()
