"""
Reference (target) daily tables. Each reference SOURCE is kept in its own table and is never merged with another:

    era5_land_cds   ERA5-Land reanalysis proxy (research/era5_land + CDS; ~5-day latency; a model, NOT observation)
    isd_station     NOAA ISD station observations (independent, but not at the pilot Panchayats)

Contract of a reference daily table (one source per table):
    reference_source, <key> (location id), target_local_date (YYYY-MM-DD, IST), temperature_min_c, temperature_max_c,
    rainfall_mm, humidity_pct, wind_kmph   -- a day exists only if all 24 hourly values were present (daily_bridge rule).

Daily statistics use the SAME rules as daily_bridge (min/max/sum/mean/max over the local IST day), so a reference day
and an Open-Meteo local forecast day cover the same 24 local hours.
"""

import pandas as pd

from daily_bridge import aggregate, config

REFERENCE_SOURCES = ("era5_land_cds", "isd_station")
IST_OFFSET_SECONDS = 19800


def reference_daily_from_hourly(hourly: pd.DataFrame, source: str, key: str = "panchayat_id",
                                utc_offset_seconds: int = IST_OFFSET_SECONDS) -> pd.DataFrame:
    """hourly: columns key, timestamp_utc, temperature_c, rainfall_mm, relative_humidity_pct, wind_speed_kmph."""
    if source not in REFERENCE_SOURCES:
        raise ValueError(f"unknown reference source '{source}'")
    h = hourly.copy()
    ts = pd.to_datetime(h["timestamp_utc"], utc=True)
    h[config.DAY_COLUMN] = (ts + pd.Timedelta(seconds=utc_offset_seconds)).dt.strftime("%Y-%m-%d")
    daily = aggregate.to_daily(h, [key]).rename(columns={config.DAY_COLUMN: "target_local_date"})
    daily.insert(0, "reference_source", source)
    return daily


def assert_single_source(reference: pd.DataFrame) -> str:
    sources = set(reference["reference_source"].unique())
    if len(sources) != 1:
        raise ValueError(f"a reference table must contain exactly one source, got {sorted(sources)}")
    return sources.pop()
