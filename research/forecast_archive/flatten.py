"""
Raw archive -> daily table (deterministic; the raw files stay the source of truth).

Day-boundary rule: Open-Meteo returns `daily.time` as LOCAL calendar dates (timezone=auto => Asia/Kolkata for the
pilot, UTC+05:30, no DST) and `utc_offset_seconds`. A forecast's target day is exactly that local date.
Lead time:

    retrieval_local_date = date(retrieved_utc + utc_offset_seconds)
    lead_days            = target_local_date - retrieval_local_date        (0 = the same local day as retrieval)

Lead 0 is a partly elapsed day; `retrieval_local_hour` is kept so analyses can exclude or stratify it.
UTC calendar days are never used for pairing.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from forecast_archive import schema
from forecast_archive.collector import DEFAULT_ROOT, read_jsonl


def local_datetime(retrieved_utc: str, utc_offset_seconds: int) -> datetime:
    return datetime.strptime(retrieved_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) + timedelta(seconds=utc_offset_seconds)


def lead_days(retrieved_utc: str, utc_offset_seconds: int, target_local_date: str) -> int:
    return (datetime.strptime(target_local_date, "%Y-%m-%d").date() - local_datetime(retrieved_utc, utc_offset_seconds).date()).days


def flatten(root: Path = DEFAULT_ROOT, verify_hashes: bool = True) -> pd.DataFrame:
    root = Path(root)
    rows = []
    for rec in read_jsonl(root / "index.jsonl"):
        if rec.get("is_mock") or rec.get("provider") != schema.PROVIDER:
            raise ValueError(f"non-provider record in archive: {rec['record_id']}")      # mock/other data must never be here
        raw = (root / rec["raw_path"]).read_bytes()
        if verify_hashes and hashlib.sha256(raw).hexdigest() != rec["raw_sha256"]:
            raise ValueError(f"raw file hash mismatch for {rec['record_id']}")
        doc = json.loads(raw)
        daily, off = doc["daily"], int(doc["utc_offset_seconds"])
        loc_dt = local_datetime(rec["retrieved_utc"], off)
        for i, day in enumerate(daily["time"]):
            vals = {schema.DAILY_FIELD_MAP[k]: daily[k][i] for k in schema.DAILY_FIELD_MAP}
            rows.append({
                "record_id": rec["record_id"], "location_id": rec["location_id"], "location_set": rec["location_set"], "role": rec["role"],
                "provider": rec["provider"], "is_mock": rec["is_mock"], "retrieved_utc": rec["retrieved_utc"],
                "retrieval_local_date": loc_dt.date().isoformat(), "retrieval_local_hour": loc_dt.hour, "utc_offset_seconds": off,
                "timezone": doc.get("timezone"), "target_local_date": day, "lead_days": lead_days(rec["retrieved_utc"], off, day),
                "response_latitude": doc.get("latitude"), "response_longitude": doc.get("longitude"), "response_elevation_m": doc.get("elevation"),
                "raw_sha256": rec["raw_sha256"], "raw_path": rec["raw_path"],
                "any_value_missing": any(v is None for v in vals.values()), **vals,
            })
    return pd.DataFrame(rows, columns=schema.DAILY_TABLE_FIELDS)
