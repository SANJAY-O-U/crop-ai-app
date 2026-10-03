"""
Deterministic Stage 4 candidate selection (pre-specified; no randomness).

Eligible pool: Taluka Panchayats the feasibility audit marked
RECOMMEND_FOR_SHORTLIST. CONDITIONAL ones are held out until the ERA5-Land
land/sea check (land_sea.py) is done; EXCLUDE and the frozen Yelandur
reference are never selected.

Procedure: for round in 1..PER_REGIME, for regime in REGIMES order, pick the
eligible candidate of that regime which
  1. has >= MIN_NEW_CELLS ERA5-Land cells,
  2. is in a Zila Panchayat not already represented,
  3. has every cell >= MIN_SEPARATION_CELLS (Chebyshev, in 0.1 deg cells)
     from every cell of every already-selected Taluka Panchayat AND of
     Yelandur, so no two selected areas are neighbouring-cell geography,
and among those MAXIMIZES the minimum great-circle distance from its
centroid to the centroids of Yelandur and all already-selected areas
(farthest-point / maximin sampling -> geographic spread, not size).
Ties: more cells, then higher COMPLETE share, then lower LGD code.
"""

from pipeline.coordinates import haversine_km
from stage4_spatial_generalization import grid
from stage4_spatial_generalization.regimes import REGIMES

PER_REGIME = 2
MIN_NEW_CELLS = 6
MIN_SEPARATION_CELLS = 3
ONE_PER_ZILA_PANCHAYAT = True


def min_cell_separation(cells_a, cells_b) -> int | None:
    if not cells_a or not cells_b:
        return None
    return min(grid.chebyshev_cells(a, b) for a in cells_a for b in cells_b)


def select(candidates: list[dict], reference: dict) -> tuple[list[dict], list[dict]]:
    """candidates: dicts with tp_code, tp_name, zp_code, regime, centroid (lat, lon),
    cells (set of (lat, lon)), complete_share. reference: Yelandur dict (centroid, cells).
    Returns (selected in pick order with round/score, selection log)."""
    pool = sorted(candidates, key=lambda c: c["tp_code"])  # input order never matters
    selected, log = [], []
    for rnd in range(1, PER_REGIME + 1):
        for regime in REGIMES:
            taken_zp = {s["zp_code"] for s in selected}
            taken_cells = set(reference["cells"]).union(*(s["cells"] for s in selected)) if selected else set(reference["cells"])
            anchors = [reference["centroid"]] + [s["centroid"] for s in selected]
            options = []
            for c in pool:
                if c["regime"] != regime or c["tp_code"] in {s["tp_code"] for s in selected} or len(c["cells"]) < MIN_NEW_CELLS:
                    continue
                if ONE_PER_ZILA_PANCHAYAT and c["zp_code"] in taken_zp:
                    continue
                if min_cell_separation(c["cells"], taken_cells) < MIN_SEPARATION_CELLS:
                    continue
                maximin = min(haversine_km(*c["centroid"], *a) for a in anchors)
                options.append((-maximin, -len(c["cells"]), -c["complete_share"], c["tp_code"], c, maximin))
            if not options:
                log.append({"round": rnd, "regime": regime, "picked": None, "reason": "no candidate satisfies the constraints"})
                continue
            options.sort(key=lambda o: o[:4])
            best, score = options[0][4], options[0][5]
            selected.append({**best, "selection_round": rnd, "maximin_distance_km": score})
            log.append({"round": rnd, "regime": regime, "picked": best["tp_code"], "picked_name": best["tp_name"],
                        "maximin_distance_km": score, "n_options": len(options)})
    return selected, log


def not_selected_reason(c: dict, selected: list[dict], reference: dict) -> str:
    if len(c["cells"]) < MIN_NEW_CELLS:
        return f"only {len(c['cells'])} ERA5-Land cells (< {MIN_NEW_CELLS})"
    same_zp = [s for s in selected if s["zp_code"] == c["zp_code"]]
    if ONE_PER_ZILA_PANCHAYAT and same_zp:
        return f"Zila Panchayat already represented by {same_zp[0]['tp_name']}"
    if min_cell_separation(c["cells"], reference["cells"]) < MIN_SEPARATION_CELLS:
        return f"within {MIN_SEPARATION_CELLS} cells of the frozen Yelandur reference"
    near = [s for s in selected if min_cell_separation(c["cells"], s["cells"]) < MIN_SEPARATION_CELLS]
    if near:
        return f"within {MIN_SEPARATION_CELLS} cells of selected {near[0]['tp_name']}"
    return f"regime quota ({PER_REGIME}) filled by candidates with larger maximin distance"
