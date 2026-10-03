"""
Reproducible entry point of the OFFLINE daily evaluation bridge. Nothing is deployed, no model is saved.

    python research/daily_bridge/run_experiment.py            # writes results/daily_bridge_results.json + REPORT.md
    python research/daily_bridge/run_experiment.py --skip-observations

Evaluation against the ERA5-Land reanalysis proxy -- not observation. The station diagnostic (Stage 5 data) is
reported separately and never pooled with the proxy results.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_RESEARCH = Path(__file__).resolve().parents[1]
_ROOT = _RESEARCH.parent
if str(_RESEARCH) not in sys.path:
    sys.path.insert(0, str(_RESEARCH))

from daily_bridge import aggregate, baselines, candidates, config, decision, metrics, splits  # noqa: E402
from ml_stage2 import features as s2_features  # noqa: E402
from ml_stage2 import model as s2_model  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
METHODS = [config.BLOCK, config.PRODUCTION, config.OFFSET] + config.CANDIDATES
FRAMING = "Evaluation against the ERA5-Land reanalysis proxy -- not observation."


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args) -> str:
    try:
        return subprocess.run(["git", *args], cwd=_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unavailable"


def build_daily_tables(data: pd.DataFrame):
    """Daily targets, block-level daily inputs and static features. Rows: primary (COMPLETE) GPs only."""
    primary = data[data["in_primary_population"] & (data["coverage_status"] == "COMPLETE")]
    target_h = aggregate.hourly_wide(primary, "target_value", ["gp_name"])
    target_d = aggregate.to_daily(target_h, ["gp_name"])
    # Block-level input: ONE coarse series per timestamp = mean over the primary GPs of the ERA5 0.25 deg
    # bilinear value (same value for every Panchayat, like a block forecast). Inputs only -- no target is used.
    block_h = (primary.groupby(["timestamp_utc", config.DAY_COLUMN, "variable"])["coarse_bilinear_value"].mean()
               .unstack("variable").reset_index())
    block_h["block"] = "block"
    block_d = aggregate.to_daily(block_h, ["block"]).drop(columns="block")
    static = primary.drop_duplicates("gp_name").set_index("gp_name")[
        ["cell_group_id", "elevation_mean_m", "elevation_range_m", "panchayat_lgd_code"]]
    return primary, target_d, block_d, static


def main(skip_obs: bool) -> dict:
    t0 = time.time()
    data_path = _ROOT / config.DATASET
    cols = ["gp_name", "cell_group_id", "panchayat_lgd_code", "coverage_status", "in_primary_population", "timestamp_utc",
            config.DAY_COLUMN, "variable", "target_value", "coarse_bilinear_value", "elevation_mean_m", "elevation_range_m",
            "centroid_to_cell_km", "intersecting_cell_count"] + config.FOLD_COLUMNS
    data = pd.read_parquet(data_path, columns=cols)
    primary, target_d, block_d, static = build_daily_tables(data)
    gps = sorted(static.index)
    block_elev = float(static["elevation_mean_m"].mean())
    cell_group_of = static["cell_group_id"].to_dict()
    block_cols = {v: f"block_{v}" for v in config.DAILY_VARIABLES}

    # production baseline per GP (the real backend function)
    prod = []
    for gp in gps:
        p = baselines.production_baseline(block_d, block_elev, float(static.loc[gp, "elevation_mean_m"]))
        p["gp_name"] = gp
        prod.append(p)
    prod = pd.concat(prod, ignore_index=True).rename(columns={v: f"prod_{v}" for v in config.DAILY_VARIABLES})

    table = target_d.merge(block_d.rename(columns=block_cols), on=config.DAY_COLUMN, how="left")
    table = table.merge(prod, on=["gp_name", config.DAY_COLUMN], how="left")
    table["elevation_mean_m"] = table["gp_name"].map(static["elevation_mean_m"])
    table["elevation_range_m"] = table["gp_name"].map(static["elevation_range_m"])
    table["elevation_delta_m"] = table["elevation_mean_m"] - block_elev
    dates = pd.to_datetime(table[config.DAY_COLUMN].astype(str))
    table = pd.concat([table, candidates.day_of_year_features(dates)], axis=1)

    long_rows, split_audits = [], {}
    temp_rows = primary[primary["variable"] == "temperature_c"]
    for fold_col in config.FOLD_COLUMNS:
        lab = splits.daily_labels(temp_rows, fold_col)
        held = sorted(set(temp_rows.loc[temp_rows[fold_col] == "test", "cell_group_id"]))
        assert len(held) == 1, f"{fold_col}: expected one held-out cell group, got {held}"
        split_audits[fold_col] = splits.audit(lab, cell_group_of, held[0])
        t = table.merge(lab, on=["gp_name", config.DAY_COLUMN], how="left")
        train_all, test_all = t[t["label"] == "train"], t[t["label"] == "test"]
        test_gps = sorted(test_all["gp_name"].unique())
        hourly_daily = candidates.hourly_candidate_daily(data[data["gp_name"].isin(gps)], fold_col, test_gps)
        hourly_daily = hourly_daily.rename(columns={v: f"hourly_{v}" for v in config.DAILY_VARIABLES})
        test_all = test_all.merge(hourly_daily, on=["gp_name", config.DAY_COLUMN], how="left")
        for dv in config.DAILY_VARIABLES:
            tr = train_all.dropna(subset=config.DAILY_FEATURES + [dv])
            te = test_all.dropna(subset=config.DAILY_FEATURES + [dv, f"prod_{dv}", f"hourly_{dv}"])
            preds = candidates.fit_predict_daily(tr, te, dv)
            out = pd.DataFrame({"fold": fold_col, "gp_name": te["gp_name"].to_numpy(), "date": te[config.DAY_COLUMN].to_numpy(),
                                "variable": dv, "target": te[dv].to_numpy(),
                                config.BLOCK: te[block_cols[dv]].to_numpy(), config.PRODUCTION: te[f"prod_{dv}"].to_numpy(),
                                "C_hourly_agg": te[f"hourly_{dv}"].to_numpy()})
            for m, p in preds.items():
                out[m] = candidates.clip_physical(dv, p)
            out[config.OFFSET] = candidates.clip_physical(
                dv, baselines.constant_offset(tr[dv], tr[block_cols[dv]], te[block_cols[dv]]))
            long_rows.append(out)
        print(f"[{time.time() - t0:6.0f}s] {fold_col} done (held-out {held[0]}, train days={len(train_all)}, test days={len(test_all)})", flush=True)
    long = pd.concat(long_rows, ignore_index=True)
    long = long.dropna(subset=["target", config.BLOCK])
    long["quarter"] = "Q" + pd.to_datetime(long["date"].astype(str)).dt.quarter.astype(str)
    long["day_code"] = pd.to_datetime(long["date"].astype(str)).map(pd.Timestamp.toordinal)

    results, decisions = {}, {}
    for dv in config.DAILY_VARIABLES:
        g = long[long["variable"] == dv]
        entry = {"unit": config.AGGREGATION[dv]["unit"], "n_pooled": int(len(g)), "methods": {}, "by_fold": {}, "by_quarter": {}, "skill": {}}
        for m in METHODS:
            entry["methods"][m] = metrics.error_metrics(g[m], g["target"])
        for fold, gf in g.groupby("fold"):
            entry["by_fold"][fold] = {"held_out_cell_group": split_audits[fold]["held_out_cell_group"], "n": int(len(gf)),
                                      "methods": {m: metrics.error_metrics(gf[m], gf["target"]) for m in METHODS}}
        for q, gq in g.groupby("quarter"):
            entry["by_quarter"][q] = {"n": int(len(gq)), "methods": {m: metrics.error_metrics(gq[m], gq["target"]) for m in METHODS}}
        dv_dec = {}
        for m in [config.PRODUCTION, config.OFFSET] + config.CANDIDATES:
            sk = metrics.skill_scores(entry["methods"][m], entry["methods"][config.BLOCK])
            tol = config.SKILL_ZERO_TOLERANCE
            fold_pos = sum(1 for f in entry["by_fold"].values()
                           if (metrics.skill(f["methods"][m]["mae"], f["methods"][config.BLOCK]["mae"]) or -1) > tol)
            q_pos = sum(1 for q in entry["by_quarter"].values()
                        if (metrics.skill(q["methods"][m]["mae"], q["methods"][config.BLOCK]["mae"]) or -1) > tol)
            boot = metrics.bootstrap_skill(g["day_code"], g[m].to_numpy(float), g[config.BLOCK].to_numpy(float), g["target"].to_numpy(float))
            vs_prod = None if m == config.PRODUCTION else metrics.skill(entry["methods"][m]["mae"], entry["methods"][config.PRODUCTION]["mae"])
            vs_off = None if m == config.OFFSET else metrics.skill(entry["methods"][m]["mae"], entry["methods"][config.OFFSET]["mae"])
            entry["skill"][m] = {"vs_block": sk, "labels_vs_block": {k: metrics.skill_label(v) for k, v in sk.items()},
                                 "folds_mae_positive_of_4": fold_pos, "quarters_mae_positive_of_4": q_pos,
                                 "bootstrap_vs_block": boot, "mae_skill_vs_production_baseline": vs_prod,
                                 "mae_skill_vs_constant_offset_diagnostic": vs_off}
            if m in config.CANDIDATES:
                dv_dec[m] = decision.decide(dv, {
                    "pooled_mae_skill": sk["mae"], "pooled_rmse_skill": sk["rmse"], "folds_mae_positive": fold_pos,
                    "quarters_mae_positive": q_pos, "ci_lower_mae_skill": boot["mae"]["ci95"][0], "mae_skill_vs_production": vs_prod})
        decisions[dv] = dv_dec
        results[dv] = entry

    obs = None
    if not skip_obs:
        try:
            from daily_bridge import observations
            obs = observations.diagnostic()
        except Exception as exc:  # noqa: BLE001 -- recorded, never hidden
            obs = {"unavailable": f"{type(exc).__name__}: {exc}"}

    out = {
        "type": "daily_evaluation_bridge", "framing": FRAMING,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runtime_s": round(time.time() - t0, 1),
        "provenance": {"git_commit": git("rev-parse", "HEAD"),
                       "uncommitted_paths_under_research_or_backend": git("status", "--porcelain", "--", "research", "backend").splitlines()[:50],
                       "dataset": config.DATASET, "dataset_sha256": sha256(data_path), "dataset_rows": int(len(data)),
                       "python": sys.version.split()[0], "pandas": pd.__version__, "numpy": np.__version__},
        "aggregation": aggregate.aggregation_table(),
        "day_definition": "IST local calendar day (Phase 2D local_date_ist, UTC+05:30, as Open-Meteo timezone=auto for Karnataka). "
                          "A daily value requires all 24 hourly values; the 2021-01-01 IST day is incomplete and drops out.",
        "block_input_definition": "Per timestamp, the mean over the 10 primary Yelandur GPs of the ERA5 0.25 deg bilinear value (the same "
                                  "value for every Panchayat, like a block forecast), then aggregated to daily. Block elevation = mean of the 10 "
                                  "GP mean elevations. A dataset-derived proxy for a block forecast: reanalysis, not an NWP forecast.",
        "methods": {config.BLOCK: "block daily value unchanged",
                    config.PRODUCTION: "backend/app/downscaling/baseline.py::apply_baseline (imported) on the block daily values with the GP-vs-block elevation difference",
                    config.OFFSET: "DIAGNOSTIC (not a candidate): block value + one constant, the mean (target - block) over the fold's train days; shows how much of any gain is plain bias removal. Not part of the pre-declared evidence rule.",
                    "C_daily_hgb": "Stage 2 HGB config on daily production-grain features",
                    "R_daily_ridge": "Stage 1 ridge definition on the same daily features",
                    "C_hourly_agg": "Stage 3A C4 hourly model, predictions clipped to physical bounds then aggregated to daily (needs hourly inputs the live API lacks: reference only)"},
        "features_daily": config.DAILY_FEATURES, "model_config_hgb": s2_model.CONFIG, "ridge_alpha": config.RIDGE_ALPHA,
        "hourly_candidate_features": s2_features.FEATURES,
        "split": {"source": "Phase 2D hourly fold labels (unchanged), converted to daily: a GP-day is train/test only if all 24 hourly rows agree",
                  "spatial": "leave-one-ERA5-Land-cell-group-out, 4 folds; each of the 10 primary GPs is test in exactly one fold",
                  "temporal": "train 2021-01-01..2022-12-24, 7-day embargo, test 2023 (UTC); mixed/embargo days unused",
                  "validation": "no separate validation period: configurations were fixed a priori (no tuning), so no validation split is needed",
                  "audits": split_audits},
        "skill_definition": "skill = 1 - candidate_error / block_as_is_error, for MAE and RMSE; abs_bias uses |bias|. >+0.01 positive, <-0.01 negative, else zero (numbers always reported).",
        "evidence_rule": config.EVIDENCE_RULE,
        "results_by_variable": results, "decisions": decisions, "observation_diagnostic": obs,
        "limitations": [
            "Target is ERA5-Land reanalysis (a model), not observation; input is ERA5 reanalysis, not an NWP forecast.",
            "Only 4 independent spatial cell groups (10 GPs); one test year (2023, a dry year); rows within a day/cell are strongly dependent.",
            "The block input is derived from the same 10 GPs' coarse values; with 4 cell groups the elevation signal cannot be learned robustly.",
            "C_hourly_agg needs hourly inputs unavailable from the daily API; it is an upper-bound reference only.",
            "Observation diagnostic: stations are 6-17 km from Panchayat centroids, only the Stage 4D hourly model is checked there, and rainfall is not evaluable.",
            "No model is saved or deployed; no production claim follows from this evaluation."],
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "daily_bridge_results.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    long.drop(columns=["day_code"]).to_csv(RESULTS / "daily_predictions_test.csv.gz", index=False, float_format="%.4f")
    from daily_bridge import report
    (RESULTS / "REPORT.md").write_text(report.render(out), encoding="utf-8")
    print(f"done in {time.time() - t0:.0f}s -> {RESULTS}", flush=True)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-observations", action="store_true")
    main(ap.parse_args().skip_observations)
