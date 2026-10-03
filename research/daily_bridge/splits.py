"""Daily split derivation from the Phase 2D hourly fold labels (never re-randomised).

A (GP, IST day) is 'train' or 'test' in a fold only if ALL 24 of its hourly rows carry
that same label in the fold column. Days straddling the 7-day embargo, the train/test
boundary or an excluded GP are 'mixed'/'excluded' and are not used by anyone.
"""

import pandas as pd

from daily_bridge import config


def daily_labels(rows_one_variable: pd.DataFrame, fold_col: str) -> pd.DataFrame:
    g = rows_one_variable.groupby(["gp_name", config.DAY_COLUMN])[fold_col]
    agg = g.agg(["nunique", "first", "count"]).reset_index()
    label = agg["first"].where((agg["nunique"] == 1) & (agg["count"] >= config.HOURS_PER_DAY), "mixed")
    return pd.DataFrame({"gp_name": agg["gp_name"], config.DAY_COLUMN: agg[config.DAY_COLUMN], "label": label})


def audit(daily: pd.DataFrame, cell_group_of: dict, held_out_group: str, min_gap_days: int = 7) -> dict:
    """`daily`: columns gp_name, local date, label. Raises on any leakage; returns the audit record."""
    d = daily[daily["label"].isin(["train", "test"])].copy()
    d["date"] = pd.to_datetime(d[config.DAY_COLUMN])
    d["cell_group"] = d["gp_name"].map(cell_group_of)
    train, test = d[d["label"] == "train"], d[d["label"] == "test"]
    if train.empty or test.empty:
        raise ValueError("a fold has no train or no test days")
    if set(train["cell_group"]) & set(test["cell_group"]):
        raise ValueError("spatial leakage: a cell group is in both train and test")
    if set(test["cell_group"]) != {held_out_group}:
        raise ValueError("test days do not belong exclusively to the held-out cell group")
    gap = (test["date"].min() - train["date"].max()).days
    if gap < min_gap_days:
        raise ValueError(f"temporal leakage: only {gap} days between last train day and first test day")
    return {"held_out_cell_group": held_out_group,
            "train_cell_groups": sorted(set(train["cell_group"])),
            "train_days": [str(train["date"].min().date()), str(train["date"].max().date())],
            "test_days": [str(test["date"].min().date()), str(test["date"].max().date())],
            "gap_days_between_last_train_and_first_test_day": int(gap),
            "n_train_gp_days": int(len(train)), "n_test_gp_days": int(len(test)),
            "cell_groups_disjoint": True, "temporal_gap_ok": True}
