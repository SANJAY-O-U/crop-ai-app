"""
ERA5-Land land/sea resolution for Stage 4 (4A).

Offline status (checked): no land/sea information exists on disk. The 4
local ERA5-Land files (pilot, Yelandur June 2023, Yelandur multi-year) are
entirely inland and contain no missing values; no mask file or coastline
dataset is present. The CONDITIONAL candidates therefore stay UNRESOLVED
until the single small request below is made (NOT made in this stage).

ERA5-Land is a land-only product: grid points it does not treat as land
carry missing values. One hour of one variable over Karnataka therefore
identifies, for every 0.1 deg cell, whether ERA5-Land provides data there.
(ECMWF also publishes a static ERA5-Land land-sea mask on the ERA5-Land
documentation page; either source can be used, and the decision rule below
is the same.)
"""

import math

from stage4_spatial_generalization import grid

REQUEST_DATASET = "reanalysis-era5-land"
REQUEST_VARIABLE = "2m_temperature"
REQUEST_TIME = {"year": ["2023"], "month": ["01"], "day": ["01"], "time": ["00:00"]}
DECISION_RULE = "cell is ERA5-Land land iff its 2m_temperature value is not missing (NaN)"


def mask_request(all_cells: set[tuple[float, float]]) -> dict:
    """The exact single-hour CDS request covering every cell of interest,
    padded by one cell and aligned to the 0.1 deg grid."""
    lats = [c[0] for c in all_cells]
    lons = [c[1] for c in all_cells]
    s = grid.ERA5_LAND_SPACING
    area = [round(max(lats) + s, 2), round(min(lons) - s, 2), round(min(lats) - s, 2), round(max(lons) + s, 2)]
    n_lat = int(round((area[0] - area[2]) / s)) + 1
    n_lon = int(round((area[3] - area[1]) / s)) + 1
    return {
        "dataset": REQUEST_DATASET,
        "request": {"variable": [REQUEST_VARIABLE], **REQUEST_TIME, "area": area, "data_format": "netcdf"},
        "expected_grid_points": n_lat * n_lon,
        "decision_rule": DECISION_RULE,
        "auth": "existing config.get_cds_client() only",
        "performed_in_this_stage": False,
    }


def resolve(flagged_cells: dict[str, list[str]], is_land: dict[str, bool] | None) -> dict[str, dict]:
    """Per CONDITIONAL Taluka Panchayat: RESOLVED_LAND (all flagged cells are
    ERA5-Land land), NON_LAND_CELLS (drop those cells, then re-apply the audit
    criteria), or UNRESOLVED_PENDING_MASK when no mask is available."""
    out = {}
    for tp, cells in flagged_cells.items():
        if is_land is None:
            out[tp] = {"status": "UNRESOLVED_PENDING_MASK", "flagged_cells": cells}
            continue
        missing = [c for c in cells if c not in is_land]
        if missing:
            raise KeyError(f"mask does not cover {missing}")
        non_land = [c for c in cells if not is_land[c]]
        out[tp] = {"status": "NON_LAND_CELLS" if non_land else "RESOLVED_LAND",
                   "flagged_cells": cells, "non_land_cells": non_land}
    return out


def bytes_estimate(n_cells: int, bytes_per_cell_month: float, months: int = 36) -> float:
    return math.ceil(n_cells * bytes_per_cell_month * months)
