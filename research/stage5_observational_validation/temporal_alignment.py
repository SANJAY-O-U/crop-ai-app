"""
Stage 5 temporal alignment (no interpolation, no filling).

Stage 4 rows are hourly UTC valid times; ISD times are UTC (format document).
India has no daylight-saving time; no timezone conversion is needed because
both sides are UTC (IST = UTC+05:30 is used only for display elsewhere).

Point variables: an accepted report at an exact top-of-hour UTC time pairs
with the Stage 4 row at that timestamp. Missing observation -> no pair.
Rainfall: an accepted report of P hours ending at T pairs with the SUM of the
method's hourly values at T-(P-1)h ... T (each Stage 4 hourly value is the
accumulation over the hour ending at its timestamp). If any of those P model
hours is unavailable (e.g. before 2023-01-01 for the frozen test-year
predictions), the pair is dropped and counted.
"""

import numpy as np
import pandas as pd


def align_points(obs: pd.DataFrame, var: str, model: pd.DataFrame) -> pd.DataFrame:
    """model: index = timestamp_utc, columns = methods. Returns matched rows."""
    ok = obs[obs[f"{var}_status"] == "OK"][["time_utc", var]].set_index("time_utc")
    joined = ok.join(model, how="inner")
    return joined.rename(columns={var: "observed"})


def align_rain(rain: pd.DataFrame, model: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """model: hourly rainfall per method. Returns (period pairs, dropped count)."""
    ok = rain[rain["status"] == "OK"]
    rows, dropped = [], 0
    idx = model.index
    for _, r in ok.iterrows():
        p = int(r["period_h"])
        hours = pd.date_range(end=r["time_utc"], periods=p, freq="h")
        if not hours.isin(idx).all():
            dropped += 1
            continue
        sums = model.loc[hours].sum()
        rows.append({"time_utc": r["time_utc"], "period_h": p, "observed": float(r["depth_mm"]),
                     "trace": bool(r["trace"]), **sums.to_dict()})
    return pd.DataFrame(rows), dropped
