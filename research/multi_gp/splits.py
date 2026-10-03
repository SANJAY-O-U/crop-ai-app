"""
Leakage-safe fold assignment for the Phase 2D multi-GP dataset.
Pure, deterministic functions -- no randomness anywhere.

SPATIAL: one fold per ERA5-Land cell group among the COMPLETE GPs
(leave-one-cell-group-out). GPs sharing a nearest ERA5-Land cell share an
identical target series, so the cell group -- not the GP -- is the unit
that must never appear on both sides of a fold.

TEMPORAL: forward-in-time blocked holdout, identical for every spatial fold:
    train_period  2021-01-01T00Z .. 2022-12-24T23Z
    embargo       2022-12-25T00Z .. 2022-12-31T23Z  (7 days, never used)
    test_period   2023-01-01T00Z .. 2023-12-31T23Z
No individual hourly row is ever assigned at random.

Per fold, a row's role is:
    "train"    -- primary population, NOT the held-out group, train_period
    "test"     -- primary population, the held-out group, test_period
    "excluded" -- everything else (held-out group in train_period, other
                  groups in test_period, embargo, PARTIAL GPs, rows whose
                  target is missing)
"""

import pandas as pd

TRAIN_START = pd.Timestamp("2021-01-01T00:00", tz="UTC")
EMBARGO_START = pd.Timestamp("2022-12-25T00:00", tz="UTC")
TEST_START = pd.Timestamp("2023-01-01T00:00", tz="UTC")
TEST_END_EXCLUSIVE = pd.Timestamp("2024-01-01T00:00", tz="UTC")

TRAIN, TEST, EXCLUDED = "train", "test", "excluded"


def temporal_period(timestamps: pd.Series) -> pd.Series:
    ts = pd.to_datetime(timestamps, utc=True)
    if (ts < TRAIN_START).any() or (ts >= TEST_END_EXCLUSIVE).any():
        raise ValueError("timestamp outside the Phase 2D window")
    period = pd.Series("train_period", index=ts.index, dtype=object)
    period[(ts >= EMBARGO_START) & (ts < TEST_START)] = "embargo"
    period[ts >= TEST_START] = "test_period"
    return period


def spatial_folds(primary_cell_groups) -> list[str]:
    """Fold k (1-based) holds out the k-th cell group in sorted order."""
    return sorted(set(primary_cell_groups))


def fold_roles(cell_group: pd.Series, in_primary: pd.Series, period: pd.Series,
               target_missing: pd.Series, held_out_group: str) -> pd.Series:
    role = pd.Series(EXCLUDED, index=cell_group.index, dtype=object)
    usable = in_primary.astype(bool) & ~target_missing.astype(bool)
    role[usable & (cell_group != held_out_group) & (period == "train_period")] = TRAIN
    role[usable & (cell_group == held_out_group) & (period == "test_period")] = TEST
    return role
