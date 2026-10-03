"""Hourly -> daily aggregation (rules in config.AGGREGATION). Pure functions.

A day is valid for a daily variable ONLY if all 24 hourly inputs are present
(non-NaN) for that group and local day; otherwise the daily value is NaN (never
a partial-day statistic, never filled).
"""

import numpy as np
import pandas as pd

from daily_bridge import config

_FUNCS = {"max": "max", "min": "min", "sum": "sum", "mean": "mean"}


def to_daily(hourly: pd.DataFrame, keys: list[str], day_col: str = config.DAY_COLUMN,
             hours_per_day: int = config.HOURS_PER_DAY) -> pd.DataFrame:
    """`hourly`: one row per (keys, hour) with a column per HOURLY variable and `day_col`.
    Returns one row per (keys, day) with a column per DAILY variable."""
    grouped = hourly.groupby(keys + [day_col], sort=True)
    out = {}
    for daily, rule in config.AGGREGATION.items():
        col = rule["hourly"]
        if col not in hourly.columns:
            continue
        g = grouped[col]
        value = g.agg(_FUNCS[rule["agg"]])
        complete = g.count() >= hours_per_day
        out[daily] = value.where(complete)
    return pd.DataFrame(out).reset_index()


def aggregation_table() -> list[dict]:
    """input -> aggregation -> output -> units, as recorded in the results."""
    return [{"input_hourly": r["hourly"], "aggregation": f"{r['agg']} over the 24 hourly values of the IST day",
             "output_daily": d, "unit": r["unit"], "mirrors_open_meteo_field": r["open_meteo"]}
            for d, r in config.AGGREGATION.items()]


def hourly_wide(rows: pd.DataFrame, value_col: str, keys: list[str]) -> pd.DataFrame:
    """Long (variable column) -> wide: one column per hourly variable."""
    wide = rows.pivot_table(index=keys + ["timestamp_utc", config.DAY_COLUMN], columns="variable", values=value_col, aggfunc="first", dropna=False)
    wide.columns.name = None
    return wide.reset_index()
