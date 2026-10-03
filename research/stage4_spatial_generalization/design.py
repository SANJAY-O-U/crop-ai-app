"""
Stage 4A/4B: land/sea resolution status, deterministic candidate selection,
pre-acquisition fold design, and the Stage 4 acquisition manifest.

    python research/stage4_spatial_generalization/design.py

Reads the committed feasibility audit + the raw LGD/DataMeet sources (via
audit.build_gp_records). Writes only stage4_acquisition_manifest.json in
this folder. Downloads nothing; trains nothing.
"""

import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from stage4_spatial_generalization import audit, criteria, folds, grid, land_sea, selection  # noqa: E402
from stage4_spatial_generalization.regimes import REGIMES, regime_of  # noqa: E402

MANIFEST_PATH = Path(__file__).resolve().parent / "stage4_acquisition_manifest.json"
REPO = audit.REPO_ROOT
PROTECTED_ARTIFACTS = {
    "stage4_feasibility_audit": audit.RESULTS_PATH,
    "stage4_taluka_audit_csv": audit.TALUK_CSV_PATH,
    "stage1_results": _RESEARCH_DIR / "baselines" / "baseline_results.json",
    "stage2_results": _RESEARCH_DIR / "ml_stage2" / "stage2_results.json",
    "stage3a_results": _RESEARCH_DIR / "ml_stage3_ablation" / "ablation_results.json",
    "stage3b_results": _RESEARCH_DIR / "ml_stage3b_rainfall" / "rainfall_results.json",
    "phase2d_manifest": _RESEARCH_DIR / "multi_gp" / "yelandur_multi_gp_manifest.json",
    "yelandur_era5_linkage": _RESEARCH_DIR / "era5_linkage" / "yelandur_era5_linkage.json",
    "yelandur_spatial_proxy": _RESEARCH_DIR / "spatial_proxy" / "yelandur_spatial_proxy.json",
    "yelandur_elevation": _RESEARCH_DIR / "elevation" / "yelandur_elevation.json",
}


def _rel(p: Path) -> str:
    return p.resolve().relative_to(REPO).as_posix()


def _bytes_per_cell_month() -> dict:
    """Measured from the real Phase 2D monthly files (month length-weighted)."""
    from multi_gp import acquire

    land = [acquire.era5_land_path(y, m) for y, m in acquire.window_months()]
    era5 = [acquire.era5_path(y, m) for y, m in acquire.window_months()]
    if not all(p.exists() for p in land + era5):
        return {"era5_land": None, "era5": None, "note": "Phase 2D raw files absent; no measured size"}
    land_b = sum(p.stat().st_size for p in land) / len(land) / 20  # 4x5 ERA5-Land points
    era5_b = sum(sum(q.stat().st_size for q in acquire.member_paths(p)) for p in era5) / len(era5) / 16  # 4x4 points
    return {"era5_land": land_b, "era5": era5_b,
            "note": "mean monthly NetCDF bytes per grid point, measured on the 72 Phase 2D files"}


def _land_area(bounds: list[float]) -> list[float]:
    """ERA5-Land [N, W, S, E], aligned to 0.1 deg, covering all GP bounds plus one cell."""
    s = grid.ERA5_LAND_SPACING
    n = grid.era5_land_cell(bounds[3], 0)[0] + s
    so = grid.era5_land_cell(bounds[1], 0)[0] - s
    w = grid.era5_land_cell(0, bounds[0])[1] - s
    e = grid.era5_land_cell(0, bounds[2])[1] + s
    return [round(n, 2), round(w, 2), round(so, 2), round(e, 2)]


def _era5_area(cells: set) -> list[float]:
    """ERA5 [N, W, S, E], aligned to 0.25 deg: every enclosing bilinear box plus one ring."""
    s = grid.ERA5_SPACING
    lats = [c[0] for c in cells]
    lons = [c[1] for c in cells]
    return [round(math.ceil(max(lats) / s - 1e-9) * s + s, 2), round(math.floor(min(lons) / s + 1e-9) * s - s, 2),
            round(math.floor(min(lats) / s + 1e-9) * s - s, 2), round(math.ceil(max(lons) / s - 1e-9) * s + s, 2)]


def _grid_points(area: list[float], spacing: float) -> int:
    return (int(round((area[0] - area[2]) / spacing)) + 1) * (int(round((area[3] - area[1]) / spacing)) + 1)


def build() -> dict:
    audit_result = json.loads(audit.RESULTS_PATH.read_text(encoding="utf-8"))
    records, _features, _ = audit.build_gp_records()
    complete = [r for r in records if r["status"] == "COMPLETE"]

    by_tp = defaultdict(list)
    for r in complete:
        by_tp[r["tp_code"]].append(r)
    cand = {c["tp_code"]: c for c in audit_result["candidates"]}
    local_tiles = audit.local_tile_names()

    def tp_view(code: str) -> dict:
        c = cand[code]
        gps = by_tp.get(code, [])
        cells = {tuple(r["era5_land_cell"]) for r in gps}
        return {
            "tp_code": code, "tp_name": c["tp_name"], "zp_code": c["zp_code"], "zp_name": c["zp_name"],
            "regime": regime_of(c["zp_name"], c["tp_name"]),
            "centroid": (c["centroid"]["lat"], c["centroid"]["lon"]) if c["centroid"] else None,
            "cells": cells, "complete_share": c["spatial_proxy"]["complete_share"], "gps": gps,
        }

    views = {code: tp_view(code) for code in cand}
    yel = views[criteria.YELANDUR_TALUKA_PANCHAYAT_CODE]
    reference = {"centroid": yel["centroid"], "cells": yel["cells"]}

    eligible = [v for code, v in views.items() if cand[code]["decision"] == "RECOMMEND_FOR_SHORTLIST"]
    selected, log = selection.select(eligible, reference)
    sel = {s["tp_code"]: s for s in selected}

    # ---- folds ----
    fold_design = {
        "temporal_split": folds.TEMPORAL_SPLIT,
        "yelandur_role": "frozen reference: never in any training set; evaluated as an extra reference region in every fold",
        "taluka_holdout": folds.taluka_holdout(sel),
        "district_holdout": {
            "equivalent_to": "taluka_holdout",
            "reason": "the selection allows one Taluka Panchayat per Zila Panchayat, so each district holdout "
                      "removes exactly one selected Taluka Panchayat",
        } if len({s["zp_code"] for s in selected}) == len(selected) else folds.grouped_holdout(sel, "zp_code", "district"),
        "regional_holdout": folds.grouped_holdout(sel, "regime", "regime"),
        "cell_group_diagnostic": {
            "label": "DIAGNOSTIC ONLY — not a geographic generalization estimate",
            "block_cells": folds.BLOCK_CELLS, "folds_k": folds.DIAG_FOLDS, "buffer_cells": folds.BUFFER_CELLS,
            "folds": folds.cell_group_diagnostic(sel),
        },
    }

    # ---- land/sea (4A) ----
    conditional = {code: c for code, c in cand.items() if c["decision"] == "CONDITIONAL"}
    flagged = {code: c["grid"]["new_cell_centres_outside_karnataka_village_polygons"] for code, c in sorted(conditional.items())}
    shared_offline = {}
    for code, c in sorted(conditional.items()):
        if c["spatial_proxy"]["complete_gps_with_shared_village"]:
            usable = [r for r in by_tp[code] if not r["has_shared_village"]]
            n = c["administrative"]["lgd_gps"]
            shared_offline[code] = {
                "tp_name": c["tp_name"],
                "complete_gps_dropped_for_shared_village": [r["gp_code"] for r in by_tp[code] if r["has_shared_village"]],
                "complete_share_after_drop": len(usable) / n,
                "new_cells_after_drop": len({tuple(r["era5_land_cell"]) for r in usable} - reference["cells"]),
                "still_meets_share_and_cell_criteria": len(usable) / n >= criteria.MIN_COMPLETE_GP_SHARE and
                len({tuple(r["era5_land_cell"]) for r in usable} - reference["cells"]) >= criteria.MIN_NEW_CELL_GROUPS,
            }
    flagged_cells = {grid.parse_cell_id(cid) for cells in flagged.values() for cid in cells}
    all_cells_of_interest = set().union(*(s["cells"] for s in selected), reference["cells"], flagged_cells)
    selected_cells = set().union(*(s["cells"] for s in selected))
    resolution = land_sea.resolve(flagged, None)

    # ---- manifest per selected ----
    sizes = _bytes_per_cell_month()
    taluka_fold = {f["test_taluka_panchayats"][0]: f["fold_id"] for f in fold_design["taluka_holdout"]}
    regime_fold = {tp: f["fold_id"] for f in fold_design["regional_holdout"] for tp in f["test_taluka_panchayats"]}
    diag_fold = {cid: f["fold_id"] for f in fold_design["cell_group_diagnostic"]["folds"] for cid in f["test_cells"]}
    entries = []
    for s in selected:
        c = cand[s["tp_code"]]
        gps = sorted(s["gps"], key=lambda r: r["gp_code"])
        bounds = [min(r["bounds"][0] for r in gps), min(r["bounds"][1] for r in gps),
                  max(r["bounds"][2] for r in gps), max(r["bounds"][3] for r in gps)]
        land_area, era5_area = _land_area(bounds), _era5_area(s["cells"])
        tiles = c["elevation"]["glo30_tiles_required"]
        per_cell = defaultdict(list)
        for r in gps:
            per_cell[grid.cell_id(tuple(r["era5_land_cell"]))].append(r["gp_code"])
        entries.append({
            "tp_code": s["tp_code"], "tp_name": s["tp_name"], "zp_code": s["zp_code"], "zp_name": s["zp_name"],
            "geographic_regime": s["regime"],
            "selection": {"round": s["selection_round"], "maximin_distance_km": s["maximin_distance_km"]},
            "lgd": {"lgd_gram_panchayats": c["administrative"]["lgd_gps"]},
            "spatial_proxy": {**c["spatial_proxy"],
                              "complete_gps": [{"gp_code": r["gp_code"], "gp_name": r["gp_name"],
                                                "era5_land_cell": grid.cell_id(tuple(r["era5_land_cell"]))} for r in gps]},
            "expected_era5_land_cells": sorted(per_cell),
            "n_expected_era5_land_cells": len(per_cell),
            "complete_gps_per_cell": dict(sorted((k, len(v)) for k, v in per_cell.items())),
            "era5_land_request_area_nwse": land_area,
            "era5_land_request_grid_points": _grid_points(land_area, grid.ERA5_LAND_SPACING),
            "era5_request_area_nwse": era5_area,
            "era5_request_grid_points": _grid_points(era5_area, grid.ERA5_SPACING),
            "elevation": {"glo30_tiles_required": tiles,
                          "already_on_disk": sorted(t for t in tiles if t in local_tiles),
                          "to_download": sorted(t for t in tiles if t not in local_tiles),
                          "all_publicly_listed": c["elevation"]["all_tiles_publicly_listed"]},
            "distance_to_yelandur_km": c["distance_to_yelandur_km"],
            "land_sea_gate": "all expected cells must be confirmed ERA5-Land land by the 4A mask request before acquisition",
            "fold_assignment": {"taluka_holdout": taluka_fold[s["tp_code"]],
                                "district_holdout": taluka_fold[s["tp_code"]],
                                "regional_holdout": regime_fold[s["tp_code"]],
                                "cell_group_diagnostic": sorted({diag_fold[cid] for cid in per_cell})},
        })

    # ---- exclusions: every other Taluka Panchayat, exactly once ----
    exclusions = []
    for code, c in sorted(cand.items()):
        if code in sel:
            continue
        v = views[code]
        if c["decision"] == "FROZEN_EXISTING":
            cat, why = "FROZEN_REFERENCE", ["Yelandur: frozen Phase 2D reference region; never a Stage 4 training region"]
        elif c["decision"] == "EXCLUDE":
            cat, why = "AUDIT_EXCLUDE", c["reasons"]
        elif c["decision"] == "CONDITIONAL":
            cat, why = "CONDITIONAL_UNRESOLVED_PENDING_LAND_SEA_MASK", c["reasons"][3:]
        else:
            cat, why = "ELIGIBLE_NOT_SELECTED", [selection.not_selected_reason(v, selected, reference)]
        exclusions.append({"tp_code": code, "tp_name": c["tp_name"], "zp_name": c["zp_name"],
                           "geographic_regime": v["regime"], "category": cat, "reasons": why})

    n_land = sum(e["era5_land_request_grid_points"] for e in entries)
    n_era5 = sum(e["era5_request_grid_points"] for e in entries)
    return {
        "type": "Stage4AcquisitionManifest",
        "scope": "Stage 4A/4B design only: no ERA5/ERA5-Land 2021-2023 download, no model training.",
        "target_framing": "Target remains the ERA5-Land reanalysis proxy — not observation.",
        "frozen": "Yelandur and Stage 1/2/3A/3B artifacts are read-only; their SHA-256 at design time is recorded below.",
        "land_sea_4a": {
            "offline_status": "NOT RESOLVABLE OFFLINE: no ERA5-Land land/sea information on disk (all local ERA5-Land "
                              "files are inland with no missing values; no mask or coastline dataset present).",
            "conditional_taluka_panchayats": len(conditional),
            "resolution": {code: {"tp_name": cand[code]["tp_name"], **r} for code, r in resolution.items()},
            "shared_village_flag_resolved_offline": shared_offline,
            "required_acquisition": land_sea.mask_request(all_cells_of_interest),
            "applies_to": "all flagged CONDITIONAL cells AND every expected cell of the selected Taluka Panchayats (gate)",
            "effect_on_selection": "none: CONDITIONAL Taluka Panchayats are ineligible; the selection is fixed and is "
                                   "not re-run after the mask unless a selected cell proves non-land",
        },
        "selection_procedure": {
            "eligible_pool": "feasibility audit RECOMMEND_FOR_SHORTLIST only",
            "per_regime": selection.PER_REGIME, "min_new_cells": selection.MIN_NEW_CELLS,
            "min_separation_cells": selection.MIN_SEPARATION_CELLS,
            "one_per_zila_panchayat": selection.ONE_PER_ZILA_PANCHAYAT,
            "objective": "farthest-point (maximin) distance to Yelandur + already-selected centroids, per regime, "
                         "in fixed regime order; ties: more cells, higher COMPLETE share, lower LGD code",
            "regimes": REGIMES,
            "regime_source": "regimes.py — project-authored conventional grouping, NOT an official agro-climatic zonation",
            "eligible_count_by_regime": {r: sum(1 for v in eligible if v["regime"] == r) for r in REGIMES},
            "log": log,
        },
        "selected_count": len(entries),
        "selected_regime_coverage": {r: [e["tp_name"] for e in entries if e["geographic_regime"] == r] for r in REGIMES},
        "selected_totals": {
            "complete_gps": sum(len(e["spatial_proxy"]["complete_gps"]) for e in entries),
            "expected_era5_land_cells": len(selected_cells),
            "era5_land_request_grid_points": n_land,
            "era5_request_grid_points": n_era5,
            "glo30_tiles_to_download": sorted({t for e in entries for t in e["elevation"]["to_download"]}),
        },
        "acquisition_volume_estimate": {
            "bytes_per_grid_point_month": sizes,
            "per_taluka_monthly_requests": len(entries) * 36 * 2,
            "era5_land_bytes_36_months": None if sizes["era5_land"] is None else land_sea.bytes_estimate(n_land, sizes["era5_land"]),
            "era5_bytes_36_months": None if sizes["era5"] is None else land_sea.bytes_estimate(n_era5, sizes["era5"]),
            "note": "Estimate only (per-Taluka request areas, 2021-2023). Not downloaded in this stage.",
        },
        "selected": entries,
        "fold_design": fold_design,
        "exclusions": exclusions,
        "protected_artifact_sha256": {k: audit.sha256(p) for k, p in PROTECTED_ARTIFACTS.items()},
        "protected_artifact_paths": {k: _rel(p) for k, p in PROTECTED_ARTIFACTS.items()},
    }


def main() -> int:
    manifest = build()
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {MANIFEST_PATH}")
    print("selected:", [(e["tp_name"], e["geographic_regime"]) for e in manifest["selected"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
