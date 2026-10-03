"""
Forecast / reference pairing and the (training-free) evaluation protocol.

    forecast issuance (record_id, retrieved_utc)
      -> target LOCAL day (daily.time) and lead_days
      -> block daily forecast value                                  [input: real Open-Meteo, block point]
      -> production baseline = backend apply_baseline(block, elev)   [the real backend function, via daily_bridge]
      -> matching reference day for each Panchayat of the block      [target: ONE reference source]
      -> evaluation record

Nothing is trained here. A candidate correction may be supplied later as a column; the protocol keeps leads separate
(never pooled across horizons) and counts every drop.
"""

import pandas as pd

from daily_bridge import baselines, config as bridge_config, metrics
from forecast_archive import locations, reference
from forecast_archive.schema import DAILY_FIELD_MAP

VARS = list(DAILY_FIELD_MAP.values())


def build_pairs(forecast_daily: pd.DataFrame, registry: dict, reference_daily: pd.DataFrame, location_key: str = "panchayat_id") -> tuple[pd.DataFrame, dict]:
    source = reference.assert_single_source(reference_daily) if len(reference_daily) else None
    ref = reference_daily.set_index([location_key, "target_local_date"]) if len(reference_daily) else None
    out, drops = [], {"forecast_rows_missing_values": 0, "no_reference_day": 0, "mock_rows": 0}
    fc = forecast_daily[~forecast_daily["is_mock"].astype(bool)]
    drops["mock_rows"] = int(len(forecast_daily) - len(fc))
    for (record_id, loc_id), g in fc.groupby(["record_id", "location_id"]):
        pans = locations.panchayats_of(registry, loc_id)
        complete = g[~g["any_value_missing"].astype(bool)]
        drops["forecast_rows_missing_values"] += int(len(g) - len(complete))
        if complete.empty:
            continue
        block_elev = complete["response_elevation_m"].iloc[0]
        block_daily = complete.rename(columns={"target_local_date": bridge_config.DAY_COLUMN})[[bridge_config.DAY_COLUMN] + VARS].rename(
            columns={"temperature_min_c": "temperature_min_c"})
        for p in pans:
            prod = baselines.production_baseline(block_daily, float(block_elev), float(p["elevation_m"])).set_index(bridge_config.DAY_COLUMN)
            for _, row in complete.iterrows():
                day = row["target_local_date"]
                if ref is None or (p["panchayat_id"], day) not in ref.index:
                    drops["no_reference_day"] += 1
                    continue
                tgt = ref.loc[(p["panchayat_id"], day)]
                out.append({"record_id": record_id, "retrieved_utc": row["retrieved_utc"], "location_set": row["location_set"],
                            "block_id": loc_id, "panchayat_id": p["panchayat_id"], "era5_land_cell": p["era5_land_cell"],
                            "target_local_date": day, "lead_days": int(row["lead_days"]), "retrieval_local_hour": int(row["retrieval_local_hour"]),
                            "reference_source": source,
                            **{f"target_{v}": tgt[v] for v in VARS}, **{f"block_{v}": row[v] for v in VARS},
                            **{f"production_{v}": prod.loc[day, v] for v in VARS}})
    return pd.DataFrame(out), drops


def evaluate_by_lead(pairs: pd.DataFrame, variable: str = "temperature_min_c", candidate: str | None = None) -> dict:
    """Per-lead metrics for block-as-is, the production baseline and (optionally) a candidate column. Leads are NOT pooled."""
    res = {}
    for lead, g in pairs.groupby("lead_days"):
        t = g[f"target_{variable}"]
        entry = {"n": int(len(g)), "n_issuances": int(g["record_id"].nunique()), "n_target_days": int(g["target_local_date"].nunique()),
                 "methods": {"block_as_is": metrics.error_metrics(g[f"block_{variable}"], t),
                             "production_baseline": metrics.error_metrics(g[f"production_{variable}"], t)}}
        if candidate and candidate in g:
            entry["methods"]["candidate"] = metrics.error_metrics(g[candidate], t)
        base = entry["methods"]["block_as_is"]
        entry["skill_vs_block"] = {m: metrics.skill_scores(v, base) for m, v in entry["methods"].items() if m != "block_as_is"}
        res[int(lead)] = entry
    return res
