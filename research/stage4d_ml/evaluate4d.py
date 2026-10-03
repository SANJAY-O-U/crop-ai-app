"""
Stage 4D runner: cross-area spatial-generalization evaluation against the
ERA5-Land reanalysis proxy (not observation).

    python research/stage4d_ml/evaluate4d.py --scheme area        # Phase B (+ Yelandur reference)
    python research/stage4d_ml/evaluate4d.py --scheme region      # Phase C
    python research/stage4d_ml/evaluate4d.py --scheme cellblock   # Phase C (diagnostic only)
    python research/stage4d_ml/evaluate4d.py --determinism-check  # re-fit one area fold, compare hashes
    python research/stage4d_ml/evaluate4d.py --assemble           # stage4d_results.json + CSV tables

Each fold is written to results/<scheme>/<fold_id>.json as soon as it
finishes; completed folds are skipped on restart (idempotent, deterministic).
Writes only inside research/stage4d_ml/. No model object is serialized; the
exact configuration, feature lists, per-fold coefficients/iterations and a
SHA-256 of every prediction vector are saved instead.
"""

import argparse
import json
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from ml_stage2.features import VARIABLES  # noqa: E402
from stage4d_ml import data4d, leakage_checks, metrics4d, splits4d, train4d  # noqa: E402

MODULE = Path(__file__).resolve().parent
RESULTS = MODULE / "results"
RESULTS_JSON = MODULE / "stage4d_results.json"
MODELS_DIR = MODULE / "models"
EVALUATION_STATEMENT = "Performance against the ERA5-Land reanalysis proxy — not observation."
SPATIAL_STATEMENT = ("Results are exploratory: 11 areas (6 regions) and 110 ERA5-Land cells from one 3-year window; "
                     "they do not establish observational accuracy or deployment readiness.")
KARWAR = {"tp_code": "6253", "tp_name": "Karwar",
          "note": ("KARWAR EXCEPTION: the frozen selection required >= 6 ERA5-Land cells. The Stage 4C land/sea "
                   "audit found E5L_14.90N_74.10E is sea; Majali (220655) and Mudgeri (220657) were excluded as "
                   "NON_LAND_TARGET_CELL with no neighbouring-cell substitution. Karwar is evaluated with 14 "
                   "Panchayats and 5 cells, BELOW the original >= 6-cell criterion.")}
DETERMINISM_FOLD = "taluka_296820"  # smallest held-out area (Nidagundi)


def versions() -> dict:
    import pyarrow
    import sklearn

    return {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__, "pyarrow": pyarrow.__version__}


def _area_names() -> dict:
    sel = data4d.load_json(data4d.DESIGN_MANIFEST)["selected"]
    return {e["tp_code"]: {"tp_name": e["tp_name"], "zp_code": e["zp_code"], "district": e["zp_name"],
                           "region": e["geographic_regime"]} for e in sel}


def _gp_static(wide: pd.DataFrame, rows: np.ndarray) -> pd.DataFrame:
    return wide.loc[rows, ["panchayat_lgd_code", "elevation_mean_m", "elevation_range_m",
                           "coarse_nearest_distance_km", "cell_group_id"]].drop_duplicates("panchayat_lgd_code")


def fold_geography(wide, scheme, fold, train, test) -> dict:
    names = _area_names()
    te, tr = _gp_static(wide, test), _gp_static(wide, train)
    tr_lo, tr_hi = float(tr["elevation_mean_m"].min()), float(tr["elevation_mean_m"].max())
    outside = te[(te["elevation_mean_m"] < tr_lo) | (te["elevation_mean_m"] > tr_hi)]
    tps = sorted(wide.loc[test, "taluka_panchayat_lgd_code"].astype(str).unique())
    return {
        "held_out_areas": [{"tp_code": t, **names[t]} for t in tps],
        "n_panchayats": int(len(te)), "n_target_cells": int(te["cell_group_id"].nunique()),
        "test_gp_elevation_mean_m": {"min": float(te["elevation_mean_m"].min()), "max": float(te["elevation_mean_m"].max()),
                                     "mean": float(te["elevation_mean_m"].mean())},
        "train_gp_elevation_mean_m": {"min": tr_lo, "max": tr_hi, "mean": float(tr["elevation_mean_m"].mean())},
        "test_gps_outside_training_elevation_range": outside["panchayat_lgd_code"].astype(str).tolist(),
        "test_mean_coarse_nearest_distance_km": float(te["coarse_nearest_distance_km"].mean()),
        "includes_karwar_exception": KARWAR["tp_code"] in tps,
    }


def _group_metrics(frame: pd.DataFrame, key: str, preds: dict, y: np.ndarray) -> list[dict]:
    rows = []
    keys = frame[key].astype(str).to_numpy()
    for m, p in preds.items():
        e = p - y
        df = pd.DataFrame({"k": keys, "abs": np.abs(e), "sq": e ** 2, "e": e})
        g = df.groupby("k", sort=True).agg(n=("e", "size"), mae=("abs", "mean"), mse=("sq", "mean"), bias=("e", "mean"))
        for k, r in g.iterrows():
            rows.append({key: k, "method": m, "n": int(r["n"]), "mae": float(r["mae"]),
                         "rmse": float(np.sqrt(r["mse"])), "bias": float(r["bias"])})
    return rows


def _pooled_parts(pred, y, variable) -> dict:
    e = pred - y
    return {"n": int(len(e)), "sum_abs": float(np.abs(e).sum()), "sum_sq": float((e ** 2).sum()),
            "sum_err": float(e.sum()), "invalid": metrics4d.invalid_count(variable, pred)}


def run_fold(wide, scheme, fold, reference=None) -> dict:
    out = {"scheme": scheme, "fold_id": fold["fold_id"], "variables": {}, "isolation": {}}
    first_train, first_test = splits4d.masks(wide, scheme, fold, VARIABLES[0])
    out["geography"] = fold_geography(wide, scheme, fold, first_train, first_test)
    for v in VARIABLES:
        out["isolation"][v] = leakage_checks.verify_fold_isolation(wide, scheme, fold, v)
        train, test = splits4d.masks(wide, scheme, fold, v)
        refs = {}
        if reference is not None:
            refs["yelandur_reference"] = (reference, (reference["temporal_period"] == "test_period").to_numpy())
        preds, ref_preds, info = train4d.fit_and_predict(wide, train, test, v, references=refs)
        y = wide.loc[test, f"target_{v}"].to_numpy(dtype=float)
        test_frame = wide.loc[test, ["panchayat_lgd_code", "cell_group_id"]]
        block = {"metrics": {m: metrics4d.summarize(p, y, v) for m, p in preds.items()},
                 "pooled_parts": {m: _pooled_parts(p, y, v) for m, p in preds.items()},
                 "model_info": info,
                 "per_gp": _group_metrics(test_frame, "panchayat_lgd_code", preds, y),
                 "per_cell": _group_metrics(test_frame, "cell_group_id", preds, y)}
        if ref_preds:
            rf, rmask = refs["yelandur_reference"]
            ry = rf.loc[rmask, f"target_{v}"].to_numpy(dtype=float)
            block["yelandur_reference"] = {
                "metrics": {m: metrics4d.summarize(p, ry, v) for m, p in ref_preds["yelandur_reference"].items()},
                "per_gp": _group_metrics(rf.loc[rmask, ["gp_name"]], "gp_name", ref_preds["yelandur_reference"], ry)}
        out["variables"][v] = block
    return out


def run_scheme(scheme: str, only_fold: str | None = None, out_dir: Path | None = None) -> list[Path]:
    identity = data4d.verify_dataset_identity()
    wide = data4d.load_stage4_wide()
    folds = splits4d.fold_definitions()
    fold_check = leakage_checks.verify_folds_against_data(wide, folds)
    feature_audit = {v: leakage_checks.feature_audit(train4d.feature_lists(v)) for v in VARIABLES}
    reference = data4d.load_yelandur_reference_wide() if scheme == "area" else None
    out_dir = out_dir or RESULTS / scheme
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "_preflight.json").write_text(json.dumps(
        {"identity": identity, "fold_check": fold_check, "feature_audit": feature_audit}, indent=2), encoding="utf-8")
    written = []
    for fold in folds[scheme]:
        if only_fold and fold["fold_id"] != only_fold:
            continue
        path = out_dir / f"{fold['fold_id']}.json"
        if path.exists() and only_fold is None:
            written.append(path)
            continue
        res = run_fold(wide, scheme, fold, reference)
        path.write_text(json.dumps(res, indent=1), encoding="utf-8")
        print(f"  {scheme} {fold['fold_id']} done", flush=True)
        written.append(path)
    return written


# ---------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------

def _load_folds(scheme: str) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((RESULTS / scheme).glob("*.json"))
            if not p.name.startswith("_")]


def _pool(parts: list[dict], variable: str) -> dict:
    n = sum(p["n"] for p in parts)
    return {"n": n, "mae": sum(p["sum_abs"] for p in parts) / n, "rmse": (sum(p["sum_sq"] for p in parts) / n) ** 0.5,
            "bias": sum(p["sum_err"] for p in parts) / n, "invalid_predictions": sum(p["invalid"] for p in parts),
            "unit": metrics4d.UNITS[variable]}


def _pool_rain(fold_metrics: list[dict]) -> dict:
    occ = {k: sum(f["rainfall"]["occurrence"][k] for f in fold_metrics) for k in ("tp", "fp", "fn", "tn")}
    tp, fp, fn = occ["tp"], occ["fp"], occ["fn"]
    wet = [f["rainfall"]["amount_on_observed_wet_hours"] for f in fold_metrics]
    nw = sum(w["n"] for w in wet)
    dry = [f["rainfall"]["dry_hour_behaviour"] for f in fold_metrics]
    nd = sum(d["n_observed_dry"] for d in dry)
    tot_p = sum(f["rainfall"]["totals"]["predicted_total_mm"] for f in fold_metrics)
    tot_o = sum(f["rainfall"]["totals"]["observed_total_mm"] for f in fold_metrics)
    return {
        "occurrence": {**occ, "precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None,
                       "f1": 2 * tp / (2 * tp + fp + fn) if tp else 0.0},
        "wet_hour_amount": {"n": nw, "mae": sum(w["n"] * w["mae"] for w in wet) / nw,
                            "rmse": (sum(w["n"] * w["rmse"] ** 2 for w in wet) / nw) ** 0.5,
                            "bias": sum(w["n"] * w["bias"] for w in wet) / nw},
        "dry_hours": {"n": nd, "mae": sum(d["n_observed_dry"] * d["mae"] for d in dry) / nd,
                      "fraction_predicted_wet": sum(d["n_observed_dry"] * d["fraction_predicted_wet"] for d in dry) / nd},
        "totals_mm": {"predicted": tot_p, "observed": tot_o, "ratio": tot_p / tot_o},
    }


def summarize_scheme(scheme: str) -> dict:
    folds = _load_folds(scheme)
    summary = {"n_folds": len(folds), "by_variable": {}, "folds": []}
    for f in folds:
        summary["folds"].append({"fold_id": f["fold_id"], "geography": f["geography"],
                                 "isolation": f["isolation"][VARIABLES[0]],
                                 "metrics": {v: {m: {k: f["variables"][v]["metrics"][m][k]
                                                     for k in ("n", "mae", "rmse", "bias", "invalid_predictions", "unit")}
                                                 for m in train4d.METHODS} for v in VARIABLES}})
    for v in VARIABLES:
        per = {}
        for m in train4d.METHODS:
            fm = [f["variables"][v]["metrics"][m] for f in folds]
            per[m] = {"fold_mean_std": metrics4d.fold_mean_std(fm),
                      "pooled": _pool([f["variables"][v]["pooled_parts"][m] for f in folds], v)}
            if v == "rainfall_mm":
                per[m]["pooled_rainfall"] = _pool_rain(fm)
        per["differences_vs_A1_bilinear_fold_mean_mae"] = {
            m: per[m]["fold_mean_std"]["mae_mean"] - per["A1_bilinear"]["fold_mean_std"]["mae_mean"] for m in train4d.METHODS}
        per["folds_where_method_mae_below_A1"] = {
            m: sum(f["variables"][v]["metrics"][m]["mae"] < f["variables"][v]["metrics"]["A1_bilinear"]["mae"] for f in folds)
            for m in train4d.METHODS}
        summary["by_variable"][v] = per
    return summary


def _spearman(x, y) -> float | None:
    x, y = pd.Series(x), pd.Series(y)
    if len(x) < 3 or x.nunique() < 2 or y.nunique() < 2:
        return None
    return float(x.rank().corr(y.rank()))


def analysis(area_folds: list[dict]) -> dict:
    rows = []
    for f in area_folds:
        g = f["geography"]
        gap = abs(g["test_gp_elevation_mean_m"]["mean"] - g["train_gp_elevation_mean_m"]["mean"])
        for v in VARIABLES:
            m = f["variables"][v]["metrics"]
            rows.append({"fold_id": f["fold_id"], "area": g["held_out_areas"][0]["tp_name"], "variable": v,
                         "elev_gap_m": gap, "elev_range_m": g["test_gp_elevation_mean_m"]["max"] - g["test_gp_elevation_mean_m"]["min"],
                         "A1_mae": m["A1_bilinear"]["mae"], "C4_mae": m["C4"]["mae"], "B_mae": m["B_ridge"]["mae"]})
    df = pd.DataFrame(rows)
    elev = {v: {"spearman_elev_gap_vs_C4_mae": _spearman(d["elev_gap_m"], d["C4_mae"]),
                "spearman_elev_gap_vs_C4_minus_A1": _spearman(d["elev_gap_m"], d["C4_mae"] - d["A1_mae"]),
                "spearman_elev_range_vs_C4_mae": _spearman(d["elev_range_m"], d["C4_mae"]), "n_areas": len(d)}
            for v, d in df.groupby("variable")}
    cells = []
    for f in area_folds:
        for v in VARIABLES:
            for r in f["variables"][v]["per_cell"]:
                if r["method"] in ("A1_bilinear", "C4"):
                    cells.append({"variable": v, "cell": r["cell_group_id"], "method": r["method"], "mae": r["mae"]})
    cdf = pd.DataFrame(cells)
    dist = {}
    if not cdf.empty:
        wide_dist = cdf.pivot_table(index=["variable", "cell"], columns="method", values="mae").reset_index()
        dm = data4d.load_json(data4d.DATASET_MANIFEST)["pairing"]
        wide_dist["coarse_km"] = wide_dist["cell"].map(lambda c: dm[c]["nearest"]["distance_km"])
        bins = pd.cut(wide_dist["coarse_km"], [0, 5, 10, 15, 25], include_lowest=True)
        for v, d in wide_dist.groupby("variable"):
            b = d.groupby(bins.loc[d.index], observed=True)[["A1_bilinear", "C4"]].mean()
            dist[v] = {"spearman_distance_vs_A1_mae": _spearman(d["coarse_km"], d["A1_bilinear"]),
                       "spearman_distance_vs_C4_mae": _spearman(d["coarse_km"], d["C4"]),
                       "n_cells": int(len(d)),
                       "binned_mean_mae": {str(k): {"A1_bilinear": float(r["A1_bilinear"]), "C4": float(r["C4"])}
                                           for k, r in b.iterrows()}}
    return {"per_area_table": rows, "elevation_relationship": elev, "coarse_distance_relationship": dist,
            "note": "Spearman correlations over 11 areas / 110 cells are exploratory, not significance tests."}


def assemble() -> dict:
    area_folds = _load_folds("area")
    pre = json.loads((RESULTS / "area" / "_preflight.json").read_text(encoding="utf-8"))
    yel = {}
    for v in VARIABLES:
        fm = {m: [f["variables"][v]["yelandur_reference"]["metrics"][m] for f in area_folds] for m in train4d.METHODS}
        yel[v] = {m: metrics4d.fold_mean_std(x) for m, x in fm.items()}
    br_df = pd.DataFrame([{**r, "variable": v} for f in area_folds for v in VARIABLES
                          for r in f["variables"][v]["yelandur_reference"]["per_gp"]
                          if r["gp_name"] == "Biligiri Ranganabetta"])
    br_summary = (br_df.groupby(["variable", "method"])[["mae", "bias"]].mean().reset_index().to_dict("records")
                  if not br_df.empty else [])
    det_path = RESULTS / "determinism_check.json"
    result = {
        "type": "Stage4DCrossAreaSpatialGeneralization",
        "evaluation_statement": EVALUATION_STATEMENT,
        "spatial_statement": SPATIAL_STATEMENT,
        "target_framing": "Target: ERA5-Land reanalysis proxy. Coarse predictor: ERA5 reanalysis. Not observational validation.",
        "karwar_exception": KARWAR,
        "dataset_identity": pre["identity"],
        "fold_integrity": pre["fold_check"],
        "feature_audit": pre["feature_audit"],
        "splits": splits4d.fold_definitions(),
        "model_configuration": train4d.model_configuration(),
        "random_state": 0,
        "versions": versions(),
        "area_holdout": summarize_scheme("area"),
        "district_holdout": {"equivalent_to": "area_holdout", "verified": pre["fold_check"]["district_equals_area"],
                             "reason": "frozen design: one selected area per district; per-row district fold IDs equal "
                                       "area fold IDs (verified), so results are identical and not re-computed"},
        "region_holdout": summarize_scheme("region") if (RESULTS / "region").exists() else None,
        "cellblock_diagnostic": ({"label": "DIAGNOSTIC ONLY — test and training cells can share an area; "
                                           "not a geographic generalization estimate",
                                  **summarize_scheme("cellblock")} if (RESULTS / "cellblock").exists() else None),
        "yelandur_reference": {
            "role": splits4d.fold_definitions()["yelandur_role"],
            "population": "Phase 2D COMPLETE GPs (Agara PARTIAL and Mamballi UNAVAILABLE excluded), 2023 test period",
            "fold_mean_std_across_area_models": yel,
            "biligiri_ranganabetta_mean_over_area_models": br_summary,
        },
        "analysis": analysis(area_folds),
        "determinism_check": json.loads(det_path.read_text(encoding="utf-8")) if det_path.exists() else None,
    }
    RESULTS_JSON.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    _write_tables(result, area_folds)
    MODELS_DIR.mkdir(exist_ok=True)
    (MODELS_DIR / "model_configuration.json").write_text(json.dumps(
        {"model_configuration": result["model_configuration"], "feature_lists": {v: train4d.feature_lists(v) for v in VARIABLES},
         "random_state": 0, "versions": result["versions"],
         "note": "No fitted model objects are saved; configurations are frozen and fits are deterministic."}, indent=1),
        encoding="utf-8")
    return result


def _write_tables(result: dict, area_folds: list[dict]) -> None:
    tables = RESULTS / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    for scheme_key in ("area_holdout", "region_holdout", "cellblock_diagnostic"):
        s = result.get(scheme_key)
        if not s:
            continue
        rows = []
        for f in s["folds"]:
            g = f["geography"]
            for v, ms in f["metrics"].items():
                for m, x in ms.items():
                    rows.append({"fold_id": f["fold_id"], "held_out": "+".join(a["tp_name"] for a in g["held_out_areas"]),
                                 "district": "+".join(a["district"] for a in g["held_out_areas"]),
                                 "region": "+".join(sorted({a["region"] for a in g["held_out_areas"]})),
                                 "n_panchayats": g["n_panchayats"], "n_cells": g["n_target_cells"],
                                 "elev_min_m": g["test_gp_elevation_mean_m"]["min"], "elev_max_m": g["test_gp_elevation_mean_m"]["max"],
                                 "karwar_exception": g["includes_karwar_exception"], "variable": v, "method": m, **x})
        pd.DataFrame(rows).to_csv(tables / f"{scheme_key}_per_fold.csv", index=False)
    gp_rows = [{"fold_id": f["fold_id"], "variable": v, **r} for f in area_folds for v in VARIABLES
               for r in f["variables"][v]["per_gp"]]
    pd.DataFrame(gp_rows).to_csv(tables / "area_holdout_per_panchayat.csv", index=False)
    pd.DataFrame(result["analysis"]["per_area_table"]).to_csv(tables / "area_elevation_analysis.csv", index=False)


def determinism_check() -> dict:
    stored = json.loads((RESULTS / "area" / f"{DETERMINISM_FOLD}.json").read_text(encoding="utf-8"))
    tmp = RESULTS / "_determinism_rerun"
    run_scheme("area", only_fold=DETERMINISM_FOLD, out_dir=tmp)
    fresh = json.loads((tmp / f"{DETERMINISM_FOLD}.json").read_text(encoding="utf-8"))
    mismatches = [f"{v}/{m}" for v in VARIABLES for m in train4d.METHODS
                  if stored["variables"][v]["metrics"][m]["prediction_sha256"] != fresh["variables"][v]["metrics"][m]["prediction_sha256"]]
    out = {"fold_id": DETERMINISM_FOLD, "compared": len(VARIABLES) * len(train4d.METHODS),
           "prediction_hash_mismatches": mismatches, "identical": not mismatches,
           "metrics_identical": stored["variables"] == fresh["variables"]}
    (RESULTS / "determinism_check.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for p in tmp.glob("*.json"):
        p.unlink()
    tmp.rmdir()
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scheme", choices=splits4d.SCHEMES)
    ap.add_argument("--determinism-check", action="store_true")
    ap.add_argument("--assemble", action="store_true")
    a = ap.parse_args()
    if a.scheme:
        run_scheme(a.scheme)
    if a.determinism_check:
        print(determinism_check())
    if a.assemble:
        assemble()
        print(f"Wrote {RESULTS_JSON}")
