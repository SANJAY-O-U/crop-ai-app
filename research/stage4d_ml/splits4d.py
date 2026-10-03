"""
Stage 4D splits, taken EXACTLY from the frozen Stage 4 design manifest
(stage4_acquisition_manifest.json -> fold_design). No new split is created;
nothing is random.

For every fold:  train = training geography x train_period (target present)
                 test  = held-out geography x test_period
Temporal periods are the Phase 2D ones (train 2021-01-01..2022-12-24 UTC,
7-day embargo, test 2023), stored per row as `temporal_period`.

Schemes
  area      11 folds, leave-one-Taluka-Panchayat-out (primary)
  district  declared identical to `area` by the frozen design (one area per
            district) -- verified, not re-computed
  region    6 folds, leave-one-regime-out
  cellblock 5 folds, 3x3-cell blocks; the frozen buffer cells are dropped
            from training. DIAGNOSTIC ONLY.
"""

import numpy as np
import pandas as pd

from stage4d_ml.data4d import DESIGN_MANIFEST, load_json

SCHEMES = ("area", "region", "cellblock")


def fold_definitions() -> dict:
    fd = load_json(DESIGN_MANIFEST)["fold_design"]
    area = [{"fold_id": f["fold_id"], "test_tp": f["test_taluka_panchayats"], "train_tp": f["train_taluka_panchayats"]}
            for f in fd["taluka_holdout"]]
    region = [{"fold_id": f["fold_id"], "test_tp": f["test_taluka_panchayats"], "train_tp": f["train_taluka_panchayats"]}
              for f in fd["regional_holdout"]]
    cellblock = [{"fold_id": f["fold_id"], "test_cells": f["test_cells"],
                  "buffer_cells": f["buffer_cells_excluded_from_training"]}
                 for f in fd["cell_group_diagnostic"]["folds"]]
    return {"area": area, "district": fd["district_holdout"], "region": region, "cellblock": cellblock,
            "temporal_split": fd["temporal_split"], "yelandur_role": fd["yelandur_role"]}


def masks(wide: pd.DataFrame, scheme: str, fold: dict, variable: str) -> tuple[np.ndarray, np.ndarray]:
    """(train_mask, test_mask) as boolean arrays over `wide`."""
    period = wide["temporal_period"].to_numpy()
    has_target = wide[f"target_{variable}"].notna().to_numpy()
    if scheme in ("area", "region"):
        tp = wide["taluka_panchayat_lgd_code"].astype(str).to_numpy()
        in_test = np.isin(tp, fold["test_tp"])
        in_train = np.isin(tp, fold["train_tp"])
    elif scheme == "cellblock":
        cell = wide["cell_group_id"].astype(str).to_numpy()
        in_test = np.isin(cell, fold["test_cells"])
        in_train = ~in_test & ~np.isin(cell, fold["buffer_cells"])
    else:
        raise ValueError(scheme)
    train = in_train & (period == "train_period") & has_target
    test = in_test & (period == "test_period")
    return train, test
