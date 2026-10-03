"""Independent DIAGNOSTIC against station observations (Stage 5 data and checkpoints).

NOT Panchayat ground truth: the stations are 6-17 km from the matched Panchayat centroids (no station is
inside a Panchayat polygon) and the model is the frozen Stage 4D HOURLY C4 (a different model from the
Yelandur daily-native candidates). It therefore checks only the hourly-aggregated research correction.

Station-day statistics are computed over the SAME matched hours for observation and every model (so a sparse
SYNOP day does not understate tmax/tmin for the observation alone), and only for IST days with at least
config.OBS_MIN_MATCHED_HOURS_PER_DAY matched hours. Rainfall is not evaluated (Stage 5: no usable wet periods).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from daily_bridge import config, metrics

_RESEARCH = Path(__file__).resolve().parents[1]
if str(_RESEARCH) not in sys.path:
    sys.path.insert(0, str(_RESEARCH))

from ml_stage2.features import VARIABLES  # noqa: E402
from stage5_observational_validation import acquire_observations, observation_qc, temporal_alignment  # noqa: E402
from stage5_observational_validation import gate6 as g6  # noqa: E402

METHODS = ["A1_bilinear", "A2_nearest", "C4"]      # A1 = coarse value ("block-as-is" analogue), C4 = hourly correction
REF = "ERA5L_target"
HOURLY = {"temperature_c": ["temperature_max_c", "temperature_min_c"], "relative_humidity_pct": ["humidity_pct"],
          "wind_speed_kmph": ["wind_kmph"]}
AGG = {d: config.AGGREGATION[d]["agg"] for ds in HOURLY.values() for d in ds}


def matched_hourly_pairs() -> pd.DataFrame:
    stations = g6.load_stations()
    fold_preds = {}
    for tp in sorted(stations["tp_code"].unique()):
        cp = g6.load_checkpoint(f"taluka_{tp}")
        if cp is None:
            raise RuntimeError(f"Gate 6 checkpoint for taluka_{tp} is missing/invalid")
        fold_preds[f"taluka_{tp}"] = cp[0]
    rows = []
    for _, st in stations.iterrows():
        sid, fold_id = st["station_id"], f"taluka_{st['tp_code']}"
        p, _ = observation_qc.parse_station(acquire_observations.station_file(sid))
        points = observation_qc.qc_points(p)
        for v in HOURLY:
            f = fold_preds[fold_id][v]
            model = f[f["panchayat_lgd_code"] == st["gp_code"]].set_index("timestamp_utc")[METHODS + [REF]]
            mp = temporal_alignment.align_points(points, v, model).reset_index()
            mp = mp.rename(columns={mp.columns[0]: "time_utc"})
            mp["station_id"], mp["station_name"], mp["region"], mp["variable"] = sid, st.get("station_name", sid), st["region"], v
            rows.append(mp)
    return pd.concat(rows, ignore_index=True)


def station_days(pairs: pd.DataFrame) -> pd.DataFrame:
    """Matched-hours daily statistics per station-day and method (+ the observation)."""
    out = []
    pairs = pairs.copy()
    pairs["day"] = (pd.to_datetime(pairs["time_utc"], utc=True) + pd.Timedelta(hours=5, minutes=30)).dt.strftime("%Y-%m-%d")
    for (sid, v, day), g in pairs.groupby(["station_id", "variable", "day"]):
        if len(g) < config.OBS_MIN_MATCHED_HOURS_PER_DAY:
            continue
        for d in HOURLY[v]:
            fn = AGG[d]
            row = {"station_id": sid, "region": g["region"].iloc[0], "day": day, "daily_variable": d, "matched_hours": len(g),
                   "observed": getattr(g["observed"], fn)()}
            for m in METHODS + [REF]:
                row[m] = getattr(g[m], fn)()
            out.append(row)
    return pd.DataFrame(out)


def diagnostic() -> dict:
    pairs = matched_hourly_pairs()
    days = station_days(pairs)
    result = {"framing": "Station-observation diagnostic. Not Panchayat ground truth; model = frozen Stage 4D hourly C4 aggregated "
                         "to daily over the matched hours. Compared against A1 (coarse ERA5 value, the block-as-is analogue).",
              "min_matched_hours_per_day": config.OBS_MIN_MATCHED_HOURS_PER_DAY,
              "stations": sorted(days["station_id"].unique().tolist()) if len(days) else [], "by_variable": {}}
    for d, g in days.groupby("daily_variable"):
        entry = {"n_station_days": int(len(g)), "per_station_days": g.groupby("station_id").size().to_dict(), "methods": {}, "per_station": {}}
        for m in METHODS + [REF]:
            entry["methods"][m] = metrics.error_metrics(g[m], g["observed"])
        entry["skill_C4_vs_A1"] = metrics.skill_scores(entry["methods"]["C4"], entry["methods"]["A1_bilinear"])
        entry["skill_C4_vs_A1_label_mae"] = metrics.skill_label(entry["skill_C4_vs_A1"]["mae"])
        codes = pd.to_datetime(g["day"]).map(pd.Timestamp.toordinal).to_numpy()
        entry["bootstrap_C4_vs_A1"] = metrics.bootstrap_skill(codes, g["C4"].to_numpy(float), g["A1_bilinear"].to_numpy(float),
                                                              g["observed"].to_numpy(float))
        for sid, gs in g.groupby("station_id"):
            a, c = metrics.error_metrics(gs["A1_bilinear"], gs["observed"]), metrics.error_metrics(gs["C4"], gs["observed"])
            entry["per_station"][sid] = {"region": gs["region"].iloc[0], "n": int(len(gs)), "A1_bilinear": a, "C4": c,
                                         "skill_mae_C4_vs_A1": metrics.skill(c["mae"], a["mae"])}
        result["by_variable"][d] = entry
    result["note_rainfall"] = "Rainfall is not evaluated: Stage 5 found no usable wet observation periods (outcome INSUFFICIENT)."
    return result
