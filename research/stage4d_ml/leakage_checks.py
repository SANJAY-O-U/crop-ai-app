"""
Pre-training integrity and leakage audit for Stage 4D. Every check raises on
failure (the run stops); results are recorded in the output JSON.
"""

import numpy as np
import pandas as pd

from ml_stage2.features import FORBIDDEN_FEATURES
from stage4_spatial_generalization import grid
from stage4d_ml import splits4d

# Columns that may never be model inputs in Stage 4D (on top of Stage 2's list).
STAGE4D_FORBIDDEN = set(FORBIDDEN_FEATURES) | {
    "panchayat_lgd_code", "gp_name", "taluka_panchayat_lgd_code", "zila_panchayat_lgd_code", "district_name",
    "geographic_regime", "cell_group_id", "temporal_period", "taluka_holdout_fold", "district_holdout_fold",
    "regional_holdout_fold", "cell_diagnostic_fold", "rainfall_clamped", "coarse_nearest_distance_km",
    "timestamp_utc",
} | {f"target_{v}" for v in ("temperature_c", "dewpoint_c", "relative_humidity_pct", "rainfall_mm", "wind_speed_kmph")} \
  | {f"nearest_{v}" for v in ("temperature_c", "dewpoint_c", "relative_humidity_pct", "rainfall_mm", "wind_speed_kmph")}


def feature_audit(feature_lists: dict[str, list[str]]) -> dict:
    out = {}
    for name, feats in feature_lists.items():
        bad = sorted(set(feats) & STAGE4D_FORBIDDEN)
        if bad:
            raise RuntimeError(f"STOP: forbidden feature(s) in {name}: {bad}")
        out[name] = {"features": list(feats), "forbidden_present": bad}
    return out


def verify_folds_against_data(wide: pd.DataFrame, folds: dict) -> dict:
    """The per-row fold columns written by Stage 4C must agree with the
    frozen design manifest, and district == area."""
    pairs = wide[["taluka_panchayat_lgd_code", "taluka_holdout_fold", "district_holdout_fold",
                  "regional_holdout_fold"]].drop_duplicates().astype(str)

    def per_tp(col: str) -> dict[str, set]:
        out: dict[str, set] = {}
        for tp, v in pairs[["taluka_panchayat_lgd_code", col]].itertuples(index=False):
            out.setdefault(tp, set()).add(v)
        return out

    area_col, district_col, region_col = (per_tp("taluka_holdout_fold"), per_tp("district_holdout_fold"),
                                          per_tp("regional_holdout_fold"))
    for f in folds["area"]:
        (code,) = f["test_tp"]
        if area_col[code] != {f["fold_id"]}:
            raise RuntimeError(f"STOP: area fold mismatch for {code}")
        if district_col[code] != {f["fold_id"]}:
            raise RuntimeError(f"STOP: district fold is not identical to area fold for {code}")
    for f in folds["region"]:
        for code in f["test_tp"]:
            if region_col[code] != {f["fold_id"]}:
                raise RuntimeError(f"STOP: region fold mismatch for {code}")
    diag = {c: f["fold_id"] for f in folds["cellblock"] for c in f["test_cells"]}
    cells = wide.drop_duplicates("cell_group_id")[["cell_group_id", "cell_diagnostic_fold"]].astype(str)
    for cid, fold in cells.itertuples(index=False):
        if diag.get(cid) != fold:
            raise RuntimeError(f"STOP: cell-block fold mismatch for {cid}")
    if folds["district"].get("equivalent_to") != "taluka_holdout":
        raise RuntimeError("STOP: frozen design no longer declares district == area holdout")
    return {"area_folds": len(folds["area"]), "region_folds": len(folds["region"]),
            "cellblock_folds": len(folds["cellblock"]), "district_equals_area": True,
            "per_row_fold_columns_match_design": True}


def verify_fold_isolation(wide: pd.DataFrame, scheme: str, fold: dict, variable: str) -> dict:
    train, test = splits4d.masks(wide, scheme, fold, variable)
    gp = wide["panchayat_lgd_code"].astype(str).to_numpy()
    cell = wide["cell_group_id"].astype(str).to_numpy()
    ts = wide["timestamp_utc"]
    tr_gp, te_gp = set(gp[train]), set(gp[test])
    tr_cell, te_cell = set(cell[train]), set(cell[test])
    if tr_gp & te_gp:
        raise RuntimeError(f"STOP: Panchayat leakage in {scheme}/{fold['fold_id']}")
    if tr_cell & te_cell:
        raise RuntimeError(f"STOP: target-cell leakage in {scheme}/{fold['fold_id']}")
    gap = ts[test].min() - ts[train].max()
    if gap < pd.Timedelta(days=7):
        raise RuntimeError(f"STOP: temporal gap {gap} < 7 days in {scheme}/{fold['fold_id']}")
    if not (wide["temporal_period"].to_numpy()[train] == "train_period").all() or \
            not (wide["temporal_period"].to_numpy()[test] == "test_period").all():
        raise RuntimeError("STOP: temporal period violated")
    min_sep = min(grid.chebyshev_cells(grid.parse_cell_id(a), grid.parse_cell_id(b)) for a in te_cell for b in tr_cell)
    return {"train_rows": int(train.sum()), "test_rows": int(test.sum()),
            "train_gps": len(tr_gp), "test_gps": len(te_gp), "train_cells": len(tr_cell), "test_cells": len(te_cell),
            "shared_gps": 0, "shared_cells": 0, "temporal_gap_hours": float(gap / pd.Timedelta(hours=1)),
            "min_test_train_cell_separation": int(min_sep)}


def verify_feature_matrix(X: np.ndarray, feature_names: list[str]) -> None:
    """The matrix handed to a model must have exactly the declared columns
    and no missing values (nothing is silently imputed)."""
    if X.shape[1] != len(feature_names):
        raise RuntimeError("STOP: feature matrix width differs from declared features")
    if np.isnan(X).any():
        raise RuntimeError("STOP: NaN in feature matrix")

