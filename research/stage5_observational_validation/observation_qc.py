"""
Stage 5 parsing + quality control of ISD global-hourly reports.

Nothing is silently deleted: every report is kept in the parsed table with
per-variable status codes, and results/observation_qc_report.json counts
every exclusion by reason and station.
"""

import numpy as np
import pandas as pd

from pipeline.units import relative_humidity_pct
from stage5_observational_validation import criteria5

RAIN_FIELDS = ("AA1", "AA2", "AA3", "AA4")


def _split(series: pd.Series, n: int) -> pd.DataFrame:
    parts = series.fillna("").astype(str).str.split(",", expand=True)
    for i in range(n):
        if i not in parts.columns:
            parts[i] = ""
    return parts[list(range(n))]


def _scaled(raw: pd.Series, missing: str, scale: float) -> pd.Series:
    raw = raw.str.strip()
    out = pd.to_numeric(raw.where(raw != missing), errors="coerce") / scale
    return out


def _num(text, missing: str | None = None) -> float:
    s = str(text).strip()
    if not s or s == missing:
        return float("nan")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def parse_station(path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (point observations, rainfall period observations)."""
    df = pd.read_csv(path, dtype=str)
    t = pd.to_datetime(df["DATE"], utc=True)
    base = pd.DataFrame({"station_id": df["STATION"].str[:6] + "-" + df["STATION"].str[6:], "time_utc": t,
                         "report_type": df["REPORT_TYPE"].str.strip(), "row": np.arange(len(df))})
    tmp, dew = _split(df["TMP"], 2), _split(df["DEW"], 2)
    wnd = _split(df["WND"], 5)
    base["temperature_c"], base["temperature_qc"] = _scaled(tmp[0], "+9999", 10), tmp[1].str.strip()
    base["dewpoint_c"], base["dewpoint_qc"] = _scaled(dew[0], "+9999", 10), dew[1].str.strip()
    base["wind_speed_kmph"] = _scaled(wnd[3], "9999", 10) * 3.6
    base["wind_qc"] = wnd[4].str.strip()
    rain_rows = []
    for field in RAIN_FIELDS:
        if field not in df.columns:
            continue
        p = _split(df[field], 4)
        present = df[field].notna() & (df[field].str.strip() != "")
        for i in np.flatnonzero(present.to_numpy()):
            rain_rows.append({"station_id": base.at[i, "station_id"], "time_utc": base.at[i, "time_utc"],
                              "report_type": base.at[i, "report_type"], "row": i, "field": field,
                              "period_h": _num(p.at[i, 0]),
                              "depth_mm": _num(p.at[i, 1], missing="9999") / 10,
                              "condition": p.at[i, 2].strip(), "qc": p.at[i, 3].strip()})
    return base, pd.DataFrame(rain_rows)


def qc_points(obs: pd.DataFrame) -> pd.DataFrame:
    """Adds <var>_status per variable: OK or the exclusion reason."""
    out = obs.copy()
    on_hour = out["time_utc"].dt.minute == 0
    for var, qc_col in (("temperature_c", "temperature_qc"), ("dewpoint_c", "dewpoint_qc"), ("wind_speed_kmph", "wind_qc")):
        status = pd.Series("OK", index=out.index, dtype=object)
        status[out[var].isna()] = "MISSING_SENTINEL"
        status[(status == "OK") & ~out[qc_col].isin(criteria5.ACCEPTED_QC)] = "REJECTED_SOURCE_QC"
        lo, hi = criteria5.QC_LIMITS[var]
        status[(status == "OK") & ((out[var] < lo) | (out[var] > hi))] = "OUTSIDE_PHYSICAL_LIMITS"
        status[(status == "OK") & ~on_hour] = "OFF_HOUR_REPORT"
        out[f"{var}_status"] = status
    # dew point above temperature is physically inconsistent -> flag dewpoint
    bad_dp = (out["temperature_c_status"] == "OK") & (out["dewpoint_c_status"] == "OK") & (out["dewpoint_c"] > out["temperature_c"] + 0.5)
    out.loc[bad_dp, "dewpoint_c_status"] = "DEWPOINT_ABOVE_TEMPERATURE"
    # duplicates: first accepted report per station-hour kept
    for var in ("temperature_c", "dewpoint_c", "wind_speed_kmph"):
        ok = out[f"{var}_status"] == "OK"
        dup = ok & out[ok].duplicated(["station_id", "time_utc"], keep="first").reindex(out.index, fill_value=False)
        out.loc[dup, f"{var}_status"] = "DUPLICATE_HOUR"
    # suspicious constant runs (flag only, kept as OK_CONSTANT_RUN_FLAGGED -> excluded)
    for var in ("temperature_c", "dewpoint_c"):
        ok = out[f"{var}_status"] == "OK"
        s = out.loc[ok].sort_values("time_utc")
        run_id = (s[var] != s[var].shift()).cumsum()
        span = s.groupby(run_id)["time_utc"].transform(lambda x: (x.max() - x.min()) / pd.Timedelta(hours=1))
        flagged = s.index[span >= criteria5.QC_CONSTANT_RUN_HOURS]
        out.loc[flagged, f"{var}_status"] = "SUSPICIOUS_CONSTANT_RUN"
    rh_ok = (out["temperature_c_status"] == "OK") & (out["dewpoint_c_status"] == "OK")
    out["relative_humidity_pct"] = np.nan
    out.loc[rh_ok, "relative_humidity_pct"] = [relative_humidity_pct(t, d) for t, d in
                                               zip(out.loc[rh_ok, "temperature_c"], out.loc[rh_ok, "dewpoint_c"])]
    out["relative_humidity_pct_status"] = np.where(rh_ok, "OK", "NEEDS_BOTH_T_AND_TD")
    rh = out["relative_humidity_pct"]
    out.loc[rh_ok & ((rh < 0) | (rh > 100.5)), "relative_humidity_pct_status"] = "OUTSIDE_PHYSICAL_LIMITS"
    return out


def qc_rain(rain: pd.DataFrame) -> pd.DataFrame:
    if rain.empty:
        return rain.assign(status=pd.Series(dtype=object))
    out = rain.copy()
    status = pd.Series("OK", index=out.index, dtype=object)
    status[~out["period_h"].isin(criteria5.RAIN_ACCEPTED_PERIODS_H)] = "PERIOD_NOT_ACCEPTED"
    status[(status == "OK") & out["condition"].isin(["1", "3", "5", "6", "7", "8", "E", "I", "J"])] = "CONDITION_NOT_USABLE"
    status[(status == "OK") & ~out["qc"].isin(criteria5.ACCEPTED_QC)] = "REJECTED_SOURCE_QC"
    trace = out["condition"] == "2"
    out.loc[trace & out["depth_mm"].isna(), "depth_mm"] = 0.0
    status[(status == "OK") & out["depth_mm"].isna()] = "MISSING_SENTINEL"
    status[(status == "OK") & (out["depth_mm"] < 0)] = "NEGATIVE_RAINFALL"
    lim = criteria5.QC_LIMITS["rainfall_mm_per_h"][1]
    status[(status == "OK") & (out["depth_mm"] > lim * out["period_h"])] = "OUTSIDE_PHYSICAL_LIMITS"
    status[(status == "OK") & (out["time_utc"].dt.minute != 0)] = "OFF_HOUR_REPORT"
    ok = status == "OK"
    dup = ok & out[ok].duplicated(["station_id", "time_utc", "period_h"], keep="first").reindex(out.index, fill_value=False)
    status[dup] = "DUPLICATE_PERIOD_REPORT"
    out["status"] = status
    out["trace"] = trace
    return out


def qc_report(points: dict, rains: dict) -> dict:
    rep = {"rows_inspected": {}, "by_station": {}}
    for sid, p in points.items():
        r = rains[sid]
        st = {"reports": int(len(p)), "report_types": p["report_type"].value_counts().to_dict(),
              "variables": {}}
        for var in ("temperature_c", "dewpoint_c", "relative_humidity_pct", "wind_speed_kmph"):
            vc = p[f"{var}_status"].value_counts().to_dict()
            st["variables"][var] = {"status_counts": vc, "accepted_hours": int(vc.get("OK", 0))}
        st["variables"]["rainfall_periods"] = {
            "status_counts": r["status"].value_counts().to_dict() if len(r) else {},
            "accepted_by_period_h": r[r["status"] == "OK"]["period_h"].value_counts().sort_index().to_dict() if len(r) else {},
            "trace_reports": int(r["trace"].sum()) if len(r) else 0}
        rep["by_station"][sid] = st
    rep["rows_inspected"] = {sid: int(len(p)) for sid, p in points.items()}
    return rep
