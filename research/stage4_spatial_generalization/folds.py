"""
Stage 4 spatial evaluation folds, designed BEFORE any data acquisition.
Every fold uses the Phase 2D temporal split (train 2021-01-01..2022-12-24
UTC, 7-day embargo, test 2023); no random hourly split anywhere.

  taluka_holdout     leave-one-selected-Taluka-Panchayat-out (primary)
  district_holdout   leave-one-Zila-Panchayat-out; identical to taluka_holdout
                     when each district contributes one Taluka Panchayat
  regional_holdout   leave-one-geographic-regime-out (hardest transfer)
  cell_group_diag    DIAGNOSTIC ONLY: 3x3-cell spatial blocks assigned
                     round-robin to K folds; training drops every cell within
                     BUFFER_CELLS of a test cell. Test and training cells can
                     share a Taluka Panchayat, so this is NOT a geographic
                     generalization estimate.

Yelandur (frozen reference) is never in any training set; it is an
additional reference evaluation region in every fold.
"""

import math

from stage4_spatial_generalization import grid

BLOCK_CELLS = 3
DIAG_FOLDS = 5
BUFFER_CELLS = 1
TEMPORAL_SPLIT = {
    "train_period_utc": ["2021-01-01T00:00Z", "2022-12-24T23:00Z"],
    "embargo_utc": ["2022-12-25T00:00Z", "2022-12-31T23:00Z"],
    "test_period_utc": ["2023-01-01T00:00Z", "2023-12-31T23:00Z"],
    "note": "Identical to Phase 2D; applied inside every spatial fold.",
}


def _fold(fold_id: str, test_units: list[str], train_units: list[str], sel: dict) -> dict:
    test_cells = set().union(*(sel[u]["cells"] for u in test_units))
    train_cells = set().union(*(sel[u]["cells"] for u in train_units))
    return {
        "fold_id": fold_id,
        "test_taluka_panchayats": sorted(test_units),
        "train_taluka_panchayats": sorted(train_units),
        "n_test_cells": len(test_cells),
        "n_train_cells": len(train_cells),
        "shared_cells": len(test_cells & train_cells),
        "min_test_train_separation_cells": min(grid.chebyshev_cells(a, b) for a in test_cells for b in train_cells),
    }


def taluka_holdout(sel: dict) -> list[dict]:
    codes = sorted(sel)
    return [_fold(f"taluka_{c}", [c], [o for o in codes if o != c], sel) for c in codes]


def grouped_holdout(sel: dict, key: str, prefix: str) -> list[dict]:
    groups = sorted({sel[c][key] for c in sel})
    return [_fold(f"{prefix}_{g}", [c for c in sel if sel[c][key] == g], [c for c in sel if sel[c][key] != g], sel)
            for g in groups]


def block_of(cell: tuple[float, float]) -> tuple[int, int]:
    span = BLOCK_CELLS * grid.ERA5_LAND_SPACING
    return math.floor(cell[0] / span + 1e-9), math.floor(cell[1] / span + 1e-9)


def cell_group_diagnostic(sel: dict) -> list[dict]:
    all_cells = sorted(set().union(*(s["cells"] for s in sel.values())))
    blocks = sorted({block_of(c) for c in all_cells})
    fold_of_block = {b: i % DIAG_FOLDS for i, b in enumerate(blocks)}
    folds = []
    for k in range(DIAG_FOLDS):
        test = {c for c in all_cells if fold_of_block[block_of(c)] == k}
        buffer = {c for c in all_cells if c not in test and any(grid.chebyshev_cells(c, t) <= BUFFER_CELLS for t in test)}
        train = set(all_cells) - test - buffer
        folds.append({
            "fold_id": f"cellblock_{k}",
            "test_cells": sorted(grid.cell_id(c) for c in test),
            "buffer_cells_excluded_from_training": sorted(grid.cell_id(c) for c in buffer),
            "n_test_cells": len(test), "n_buffer_cells": len(buffer), "n_train_cells": len(train),
            "min_test_train_separation_cells": min(grid.chebyshev_cells(a, b) for a in test for b in train) if test and train else None,
        })
    return folds
