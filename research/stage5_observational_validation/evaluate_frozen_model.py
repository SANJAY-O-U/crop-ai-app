"""
Stage 5 frozen-model evaluation against independent observations.

Stage 4D was evaluated against the ERA5-Land reanalysis proxy. Stage 5
evaluates the frozen Stage 4D model against independent observations.

Frozen model: Stage 4D saved no fitted objects, only frozen configurations,
fold definitions and a SHA-256 of every prediction vector. GATE 6 (gate6.py,
its own resumable step) re-fits each needed Stage 4D area fold with the
unchanged Stage 4D code and requires the recorded hashes to be reproduced;
the verified predictions are checkpointed. This module then compares those
checkpointed predictions with observations. Observations are never passed to
any fitting code.

    python -u research/stage5_observational_validation/evaluate_frozen_model.py --step gate6   > gate6.log 2>&1
    python -u research/stage5_observational_validation/evaluate_frozen_model.py --step evaluate > evaluate.log 2>&1
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from ml_stage2.features import VARIABLES  # noqa: E402
from stage4d_ml import data4d, metrics4d, train4d  # noqa: E402
from stage5_observational_validation import (  # noqa: E402
    acquire_observations, criteria5, metrics5, observation_qc, provenance, temporal_alignment,
)
from stage5_observational_validation import gate6 as g6  # noqa: E402
from stage5_observational_validation.gate6 import METHODS, REFERENCE, log  # noqa: E402

MODULE = Path(__file__).resolve().parent
RESULTS = MODULE / "results"
FRAMING = ("Stage 4D was evaluated against the ERA5-Land reanalysis proxy. Stage 5 evaluates the frozen Stage 4D "
           "model against independent observations.")
KARWAR_NOTE = ("KARWAR EXCEPTION: Karwar is evaluated with 14 Panchayats and 5 ERA5-Land cells, below the frozen "
               ">= 6-cell criterion (E5L_14.90N_74.10E is sea; Majali 220655 and Mudgeri 220657 excluded).")


def evaluate() -> dict:
    """Observation comparison. Requires Gate 6 to be recorded and valid for every
    needed fold (run `--step gate6` first); nothing is re-fitted here."""
    log("evaluation step: verifying Stage 4C dataset identity")
    identity = data4d.verify_dataset_identity()
    stations = g6.load_stations()
    primary_count = int((stations["match_set"] == "PRIMARY").sum())

    log("checking that Gate 6 is recorded and valid for every needed fold")
    fold_preds, gate6 = {}, []
    for tp in sorted(stations["tp_code"].unique()):
        fold_id = f"taluka_{tp}"
        cp = g6.load_checkpoint(fold_id)
        needed = set(stations.loc[stations["tp_code"] == tp, "gp_code"])
        if cp is None or not needed <= set(cp[1]["keep_gps"]):
            raise RuntimeError(f"STOP: Gate 6 is not recorded/valid for {fold_id}; run --step gate6 first")
        fold_preds[fold_id], rec = cp
        gate6.append(rec)
    log(f"Gate 6 verified for {len(gate6)} fold(s); no observation has been read yet")

    log("acquiring/verifying observation files (SHA-256) and running QC")
    files = acquire_observations.run()
    points, rains = {}, {}
    for sid in stations["station_id"]:
        p, r = observation_qc.parse_station(acquire_observations.station_file(sid))
        points[sid], rains[sid] = observation_qc.qc_points(p), observation_qc.qc_rain(r)
        log(f"  QC {sid}: {len(p):,} reports parsed")
    qc = observation_qc.qc_report(points, rains)

    log("aligning observations with the frozen predictions")
    pairs, rain_pairs, alignment = [], [], {}
    for _, st in stations.iterrows():
        sid, fold_id = st["station_id"], f"taluka_{st['tp_code']}"
        alignment[sid] = {}
        for v in VARIABLES:
            f = fold_preds[fold_id][v]
            model = f[f["panchayat_lgd_code"] == st["gp_code"]].set_index("timestamp_utc")[METHODS + [REFERENCE]]
            if v == "rainfall_mm":
                rp, dropped = temporal_alignment.align_rain(rains[sid], model)
                alignment[sid][v] = {"accepted_periods": int((rains[sid]["status"] == "OK").sum()) if len(rains[sid]) else 0,
                                     "paired": int(len(rp)), "dropped_incomplete_model_window": dropped}
                if len(rp):
                    rp["station_id"] = sid
                    rain_pairs.append(rp)
                continue
            mp = temporal_alignment.align_points(points[sid], v, model)
            mp = mp.reset_index().rename(columns={"index": "time_utc", "timestamp_utc": "time_utc"})
            mp["station_id"], mp["variable"] = sid, v
            alignment[sid][v] = {"accepted_obs_hours": int((points[sid][f"{v}_status"] == "OK").sum()),
                                 "paired_hours": int(len(mp)), "model_hours_2023": int(len(model)),
                                 "missing_obs_hours_in_2023": int(len(model) - len(mp))}
            pairs.append(mp)
    pairs = pd.concat(pairs, ignore_index=True)
    rain_pairs = pd.concat(rain_pairs, ignore_index=True) if rain_pairs else pd.DataFrame()
    return summarize(stations, pairs, rain_pairs, qc, alignment, gate6, identity, files, primary_count)


def _sufficient(n: int) -> bool:
    return n >= criteria5.MIN_STATION_HOURS_FOR_METRICS


def summarize(stations, pairs, rain_pairs, qc, alignment, gate6, identity, files, primary_count) -> dict:
    meta = stations.set_index("station_id")
    st_rows, season_rows = [], []
    for (sid, v), g in pairs.groupby(["station_id", "variable"]):
        suff = _sufficient(len(g))
        for m in METHODS + [REFERENCE]:
            st_rows.append({"station_id": sid, "station_name": meta.at[sid, "station_name"], "region": meta.at[sid, "region"],
                            "area": meta.at[sid, "tp_name"], "variable": v, "method": m, "unit": metrics4d.UNITS[v],
                            "sufficient_sample": suff, **metrics5.point_metrics(g[m], g["observed"]),
                            "missing_obs_hours_in_2023": alignment[sid][v]["missing_obs_hours_in_2023"]})
        g = g.assign(season=metrics5.season_of(g["time_utc"]))
        for season, gs in g.groupby("season"):
            for m in METHODS + [REFERENCE]:
                season_rows.append({"station_id": sid, "station_name": meta.at[sid, "station_name"], "variable": v,
                                    "season": season, "method": m, "sufficient_sample": _sufficient(len(gs)),
                                    **metrics5.point_metrics(gs[m], gs["observed"])})
    station_df, season_df = pd.DataFrame(st_rows), pd.DataFrame(season_rows)

    region_rows, pooled, uncertainty, outcome = [], {}, {}, {}
    for v, g in pairs.groupby("variable"):
        log(f"pooled metrics + bootstrap: {v} ({g['station_id'].nunique()} station(s), {len(g):,} hourly pairs)")
        ok_st = [sid for sid, gs in g.groupby("station_id") if _sufficient(len(gs))]
        gp_ok = g[g["station_id"].isin(ok_st)]
        pooled[v] = {"stations": ok_st, **{m: metrics5.point_metrics(gp_ok[m], gp_ok["observed"]) for m in METHODS + [REFERENCE]}}
        for region, gr in gp_ok.groupby(gp_ok["station_id"].map(meta["region"])):
            for m in METHODS + [REFERENCE]:
                region_rows.append({"region": region, "variable": v, "method": m,
                                    "stations": ",".join(sorted(gr["station_id"].unique())),
                                    **metrics5.point_metrics(gr[m], gr["observed"])})
        unc = {}
        for base in ("A1_bilinear", "A2_nearest"):
            groups = [((np.abs(gs["C4"] - gs["observed"]) - np.abs(gs[base] - gs["observed"])).to_numpy(),
                       gs["time_utc"].dt.floor("D").to_numpy()) for _, gs in gp_ok.groupby("station_id")]
            unc[f"C4_minus_{base}"] = {
                "pooled": metrics5.paired_bootstrap(groups),
                "per_station": {sid: metrics5.paired_bootstrap([(
                    (np.abs(gs["C4"] - gs["observed"]) - np.abs(gs[base] - gs["observed"])).to_numpy(),
                    gs["time_utc"].dt.floor("D").to_numpy())]) for sid, gs in gp_ok.groupby("station_id")}}
        uncertainty[v] = unc
        a1, a2 = unc["C4_minus_A1_bilinear"]["pooled"], unc["C4_minus_A2_nearest"]["pooled"]
        if a1["ci95"] is None:
            outcome[v] = "INSUFFICIENT"
        elif a1["ci95"][1] < 0 and a2["ci95"][1] < 0:
            outcome[v] = "SUPPORTED"
        elif a1["ci95"][0] > 0 and a2["ci95"][0] > 0:
            outcome[v] = "CONTRADICTED"
        else:
            outcome[v] = "MIXED"

    rain = {"note": "Rainfall periods per station are far below MIN_STATION_HOURS_FOR_METRICS; reported descriptively only.",
            "periods_by_station": rain_pairs.groupby("station_id").size().to_dict() if len(rain_pairs) else {}}
    if len(rain_pairs):
        rain["pooled_all_periods"] = {m: metrics5.rain_metrics(rain_pairs[m], rain_pairs["observed"], rain_pairs["period_h"])
                                      for m in METHODS + [REFERENCE]}
        rain["by_period_h"] = {int(p): {"n": int(len(g)), **{m: metrics5.rain_metrics(g[m], g["observed"], g["period_h"])
                                                          for m in METHODS + [REFERENCE]}}
                               for p, g in rain_pairs.groupby("period_h")}
    outcome["rainfall_mm"] = "INSUFFICIENT"

    strata = {}
    st_attr = meta[["elevation_m", "station_to_target_cell_km", "station_minus_gp_elevation_m", "region"]].copy()
    st_attr["elevation_band"] = pd.cut(st_attr["elevation_m"], criteria5.ELEVATION_BANDS_M).astype(str)
    st_attr["distance_band_km"] = pd.cut(st_attr["station_to_target_cell_km"], [0, 10, 20, 50]).astype(str)
    for key in ("elevation_band", "distance_band_km"):
        rows = []
        for v, g in pairs.groupby("variable"):
            g = g[g["station_id"].map(lambda s: _sufficient(int((g["station_id"] == s).sum())))]
            for band, gb in g.groupby(g["station_id"].map(st_attr[key])):
                rows.append({"band": band, "variable": v, "n_stations": int(gb["station_id"].nunique()),
                             **{f"{m}_mae": metrics5.point_metrics(gb[m], gb["observed"])["mae"] for m in METHODS + [REFERENCE]}})
        strata[key] = rows

    RESULTS.mkdir(parents=True, exist_ok=True)
    station_df.to_csv(RESULTS / "station_level_results.csv", index=False)
    pd.DataFrame(region_rows).to_csv(RESULTS / "region_level_results.csv", index=False)
    season_df.to_csv(RESULTS / "seasonal_results.csv", index=False)
    (RESULTS / "observation_qc_report.json").write_text(json.dumps(qc, indent=1, default=str), encoding="utf-8")
    prov = provenance.build(files, gate6)
    (RESULTS / "provenance.json").write_text(json.dumps(prov, indent=1), encoding="utf-8")

    result = {
        "type": "Stage5ObservationalValidation",
        "framing": FRAMING,
        "terminology": ("Observations are an independent validation source with their own errors (siting, instrument, "
                        "reporting); ERA5-Land is a reanalysis proxy. Neither is treated as error-free."),
        "karwar_exception": KARWAR_NOTE,
        "evaluation_period_utc": [criteria5.EVAL_START_UTC, criteria5.EVAL_END_UTC],
        "primary_matched_station_count": primary_count,
        "primary_set_note": ("EMPTY: no ISD station lies inside an included Stage 4 Panchayat polygon. All results below "
                             "are the NEARBY DIAGNOSTIC set and must not be read as Panchayat-level validation."),
        "diagnostic_stations": stations[["station_id", "station_name", "latitude", "longitude", "elevation_m", "tp_name",
                                         "district", "region", "gp_code", "gp_name", "model_target_cell",
                                         "station_to_target_cell_km", "station_to_gp_centroid_km",
                                         "station_minus_gp_elevation_m", "match_set"]].to_dict("records"),
        "counts": {"stations": int(len(stations)), "areas": int(stations["tp_code"].nunique()),
                   "regions": sorted(stations["region"].unique().tolist()),
                   "hourly_pairs_by_variable": pairs.groupby("variable").size().to_dict()},
        "dataset_identity": {"dataset_manifest_sha256": identity["dataset_manifest_sha256"], "row_total": identity["row_total"]},
        "frozen_model": {"configuration": train4d.model_configuration(), "features_C4": train4d.C_VARIANTS["C4"],
                         "gate6_reproduction": gate6, "random_state": 0},
        "alignment": alignment,
        "pooled_sufficient_stations": pooled,
        "uncertainty": uncertainty,
        "outcome_by_variable": outcome,
        "outcome_rule": "see criteria5.py (pre-declared): SUPPORTED / CONTRADICTED / MIXED from pooled paired bootstrap",
        "rainfall": rain,
        "strata": strata,
    }
    (RESULTS / "stage5_results.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    return result


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Stage 5 frozen-model evaluation")
    ap.add_argument("--step", choices=["gate6", "evaluate", "all"], default="all",
                    help="gate6: verify/checkpoint the frozen model only (no observations); "
                         "evaluate: compare with observations (needs Gate 6); all: both in sequence")
    args = ap.parse_args()
    if args.step in ("gate6", "all"):
        g6.run_gate6()
    if args.step in ("evaluate", "all"):
        result = evaluate()
        log("outcomes: " + json.dumps(result["outcome_by_variable"]))
        log("done: wrote stage5_results.json and the station/region/seasonal CSVs")
