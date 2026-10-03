"""
Prospective Open-Meteo forecast collector (RESEARCH ONLY -- never imported by backend/ or frontend/).

    python research/forecast_archive/collector.py                       # all registry block points, one 12-h slot
    python research/forecast_archive/collector.py --sets live_demo_pilot
    python research/forecast_archive/collector.py --root /some/dir --slot-hours 12

Properties (each covered by tests):
  * The request is the production request: same URL, same daily variables, timezone=auto (only forecast_days is
    16 instead of the caller's N, so every lead 0..15 is kept). A parity test compares it with OpenMeteoProvider.
  * The exact response bytes are stored once (exclusive create, read-only) and hashed; processed values are derived
    later from that file, never stored instead of it.
  * Resumable / duplicate-free: one record per (location, UTC slot); an already-filled slot is skipped without a
    network call, and an identical response body already archived for the location is not stored twice.
  * Failures (HTTP, timeout, network, invalid JSON/shape) are logged to errors.jsonl and NEVER replaced by mock or
    synthetic data; a failed slot stays empty so a rerun retries it.
  * No MockWeatherProvider, no weather.service fallback: this module talks to the provider directly.
"""

import argparse
import hashlib
import json
import os
import stat
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
for p in (str(_HERE.parent), str(_ROOT / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

from forecast_archive import locations, schema  # noqa: E402
# Reuse the production request definition (URL + daily variables) instead of retyping it.
from app.weather.providers.open_meteo import FORECAST_URL, _DAILY_VARS  # noqa: E402

DEFAULT_ROOT = _ROOT / "data" / "raw" / "open_meteo_forecast_archive"
TIMEOUT_S = 20.0


def request_params(latitude: float, longitude: float) -> dict:
    return {"latitude": latitude, "longitude": longitude, "daily": ",".join(_DAILY_VARS),
            "timezone": "auto", "forecast_days": schema.FORECAST_DAYS}


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slot_start(dt: datetime, slot_hours: int) -> datetime:
    dt = dt.astimezone(timezone.utc)
    return dt.replace(hour=(dt.hour // slot_hours) * slot_hours, minute=0, second=0, microsecond=0)


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_jsonl(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def validate_body(body: bytes):
    """Return (parsed_json, None) or (None, reason). The shape check protects against silently archiving junk."""
    try:
        doc = json.loads(body)
    except Exception as exc:  # noqa: BLE001
        return None, f"not JSON: {type(exc).__name__}"
    daily = doc.get("daily") if isinstance(doc, dict) else None
    if not isinstance(daily, dict) or "time" not in daily:
        return None, "missing 'daily' block"
    n = len(daily["time"])
    for var in _DAILY_VARS:
        if var not in daily or not isinstance(daily[var], list) or len(daily[var]) != n:
            return None, f"daily variable '{var}' missing or wrong length"
    if "utc_offset_seconds" not in doc:
        return None, "missing utc_offset_seconds"
    return doc, None


def _http_get(url, params, timeout):
    import httpx
    return httpx.get(url, params=params, timeout=timeout)


def collect(root: Path = DEFAULT_ROOT, sets=None, slot_hours: int = schema.DEFAULT_SLOT_HOURS, now_fn=None, http_get=None,
            registry: dict | None = None, pause_s: float = 0.0) -> dict:
    """One collection pass over every block point of the registry. Returns counts."""
    root = Path(root)
    http_get = http_get or _http_get
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    registry = registry or locations.load_registry()
    index_path, errors_path = root / "index.jsonl", root / "errors.jsonl"
    index = read_jsonl(index_path)
    filled = {(r["location_id"], r["slot_start_utc"]) for r in index}
    seen_hash = {(r["location_id"], r["raw_sha256"]) for r in index}
    counts = {"stored": 0, "skipped_slot_filled": 0, "skipped_duplicate_content": 0, "errors": 0}

    for loc in locations.block_locations(registry, sets):
        now = now_fn()
        slot = utc_iso(slot_start(now, slot_hours))
        if (loc["location_id"], slot) in filled:
            counts["skipped_slot_filled"] += 1
            continue
        params = request_params(loc["latitude"], loc["longitude"])
        base_err = {"archive_version": schema.ARCHIVE_VERSION, "location_id": loc["location_id"], "location_set": loc["location_set"],
                    "slot_start_utc": slot, "request_url": FORECAST_URL, "request_params": params, "body_sha256": None, "http_status": None}

        def fail(kind, message, status=None, body=None):
            counts["errors"] += 1
            _append_jsonl(errors_path, {**base_err, "retrieved_utc": utc_iso(now_fn()), "kind": kind, "http_status": status,
                                        "message": str(message)[:300], "body_sha256": hashlib.sha256(body).hexdigest() if body else None})

        try:
            resp = http_get(FORECAST_URL, params, TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001 -- recorded, never hidden
            kind = "timeout" if "timeout" in type(exc).__name__.lower() else "network_error"
            fail(kind, f"{type(exc).__name__}: {exc}")
            continue
        retrieved = now_fn()
        body = bytes(resp.content)
        if resp.status_code != 200:
            fail("http_error", f"HTTP {resp.status_code}", resp.status_code, body)
            continue
        doc, reason = validate_body(body)
        if reason:
            fail("invalid_response", reason, resp.status_code, body)
            continue

        digest = hashlib.sha256(body).hexdigest()
        if (loc["location_id"], digest) in seen_hash:
            counts["skipped_duplicate_content"] += 1
            continue
        rel = Path("raw") / loc["location_id"] / retrieved.strftime("%Y%m%d") / f"{retrieved.strftime('%Y%m%dT%H%M%SZ')}_{digest[:12]}.json"
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "xb") as f:                      # exclusive create: a raw file can never be overwritten
            f.write(body)
        os.chmod(path, stat.S_IREAD)
        meta = {k: doc.get(k) for k in schema.RESPONSE_META_FIELDS if k not in ("n_days",)}
        meta["n_days"] = len(doc["daily"]["time"])
        record = {"archive_version": schema.ARCHIVE_VERSION, "record_id": f"{loc['location_id']}|{slot}", "location_id": loc["location_id"],
                  "location_set": loc["location_set"], "role": schema.ROLE_BLOCK_INPUT, "provider": schema.PROVIDER, "is_mock": False,
                  "retrieved_utc": utc_iso(retrieved), "slot_start_utc": slot, "request_url": FORECAST_URL, "request_params": params,
                  "http_status": resp.status_code, "raw_path": rel.as_posix(), "raw_sha256": digest, "raw_bytes": len(body), "response_meta": meta}
        _append_jsonl(index_path, record)
        filled.add((loc["location_id"], slot))
        seen_hash.add((loc["location_id"], digest))
        counts["stored"] += 1
        if pause_s:
            time.sleep(pause_s)
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--sets", nargs="*", default=None)
    ap.add_argument("--slot-hours", type=int, default=schema.DEFAULT_SLOT_HOURS)
    a = ap.parse_args()
    print(json.dumps(collect(Path(a.root), a.sets, a.slot_hours, pause_s=0.5), indent=2))
