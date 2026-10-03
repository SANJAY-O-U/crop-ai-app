"""
Statistical-readiness gate for the real-forecast experiment. It applies the FROZEN daily_bridge evidence rule
(research/daily_bridge/config.py::EVIDENCE_RULE) and never weakens it:

  * "succeed in at least 3 of 4 folds"   needs 4 independent spatial folds  -> >= 4 distinct ERA5-Land cells among
                                          the evaluated Panchayats (the Phase 2D definition of an independent group)
  * "at least 3 of 4 quarters"           needs paired target days in all 4 calendar quarters
  * "beat block-as-is / production"      needs paired (forecast, reference) records at all

    python research/forecast_archive/readiness.py            # writes results/readiness.json
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from daily_bridge import config as bridge_config  # noqa: E402
from forecast_archive import flatten, locations, pairing, reference  # noqa: E402
from forecast_archive.collector import DEFAULT_ROOT, read_jsonl  # noqa: E402

NOT_READY = "Phase 2C evaluation is not yet statistically ready; prospective forecast archiving must run first."
PROCESSED = _HERE.parents[1] / "data" / "processed" / "forecast_archive"


def assess(registry: dict, forecast_daily: pd.DataFrame, pairs: pd.DataFrame, location_set: str, index_records: list, error_records: list) -> dict:
    rule = bridge_config.EVIDENCE_RULE
    fc = forecast_daily[forecast_daily["location_set"] == location_set] if len(forecast_daily) else forecast_daily
    pr = pairs[pairs["location_set"] == location_set] if len(pairs) else pairs
    groups = locations.spatial_groups(registry, location_set)
    panchayats = [l for l in registry["locations"] if l["location_set"] == location_set and l["role"] == "panchayat"]
    quarters = sorted({f"{d[:4]}-Q{(int(d[5:7]) - 1) // 3 + 1}" for d in pr["target_local_date"]}) if len(pr) else []
    calendar_quarters = {q.split("-")[1] for q in quarters}
    counts = {
        "panchayats": len(panchayats), "unique_era5_land_cells": len({p["era5_land_cell"] for p in panchayats}), "independent_spatial_groups": groups,
        "forecast_issuances": len({r["record_id"] for r in index_records if r["location_set"] == location_set}),
        "failed_attempts": len([e for e in error_records if e["location_set"] == location_set]),
        "forecast_target_days": int(fc["target_local_date"].nunique()) if len(fc) else 0,
        "forecast_rows": int(len(fc)), "paired_target_observations": int(len(pr)),
        "leads_with_pairs": sorted(int(x) for x in pr["lead_days"].unique()) if len(pr) else [],
        "calendar_quarters_with_pairs": sorted(calendar_quarters),
    }
    checks = {
        "has_paired_forecast_reference_records": counts["paired_target_observations"] > 0,
        "four_independent_spatial_folds_available (needed by the '3 of 4 folds' rule)": groups >= 4,
        "all_four_calendar_quarters_covered (needed by the '3 of 4 quarters' rule)": len(calendar_quarters) >= 4,
    }
    ready = all(checks.values())
    return {"location_set": location_set, "counts": counts, "checks": checks, "frozen_evidence_rule": rule, "ready": ready,
            "statement": "Enough data exists to run the real-forecast experiment under the frozen rule." if ready else NOT_READY,
            "failed_checks": [k for k, v in checks.items() if not v]}


def main() -> dict:
    registry = locations.load_registry()
    index_records, error_records = read_jsonl(DEFAULT_ROOT / "index.jsonl"), read_jsonl(DEFAULT_ROOT / "errors.jsonl")
    fc = flatten.flatten(DEFAULT_ROOT) if index_records else pd.DataFrame(columns=flatten.schema.DAILY_TABLE_FIELDS)
    ref_files = sorted(PROCESSED.glob("reference_*.csv")) if PROCESSED.exists() else []
    out_sets = {}
    for s in (locations.LIVE, locations.YELANDUR):
        pairs = pd.DataFrame()
        if ref_files and len(fc):
            ref = pd.read_csv(ref_files[0])
            pairs, _ = pairing.build_pairs(fc[fc["location_set"] == s], registry, ref)
        out_sets[s] = assess(registry, fc, pairs, s, index_records, error_records)
    result = {"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "archive_root": str(DEFAULT_ROOT),
              "reference_tables_found": [p.name for p in ref_files], "by_location_set": out_sets}
    (_HERE / "results").mkdir(exist_ok=True)
    (_HERE / "results" / "readiness.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    for s, r in out_sets.items():
        print(f"[{s}] ready={r['ready']}  {r['statement']}\n   counts={json.dumps(r['counts'])}\n   failed={r['failed_checks']}")
    return result


if __name__ == "__main__":
    main()
