"""
Stage 4 FEASIBILITY AUDIT (offline, read-only): which Karnataka Taluka
Panchayats could add genuinely independent ERA5-Land spatial groups to the
frozen Yelandur experiment?

No download, no dataset build, no model. Inputs are files already on disk:

  LGD (official identity)  data/raw/lgd/pri_local_bodies.22Sep2026.csv   GP -> Taluka P. -> Zila P.
                           data/raw/lgd/villages_by_blocks.31Jul2026.csv  village -> GP
                           data/raw/lgd/villages.31Jul2026.csv            village -> Census-2001 code
  Spatial proxy            data/raw/datameet/ka.geojson                   1991-vintage village polygons
  GLO-30 availability      data/raw/elevation/tileList.txt                public tile list
  GLO-30 data (partial)    data/raw/elevation/*.tif                       only N11-N12 x E076-E077 on disk
  Frozen Yelandur cells    research/era5_linkage/yelandur_era5_linkage.json

Village -> polygon matching is EXACT CODE ONLY (LGD Census-2001 code,
zero-padded to 8, == DataMeet V_CT_CODE), reusing
spatial_proxy.matching.index_datameet_features_by_vct_code. The Yelandur
build's exact-name fallback is deliberately NOT used statewide. Invalid
source polygons are never repaired: their GP is reported INVALID_GEOMETRY.

Centroids use the Yelandur method (unary_union, centroid in EPSG:32643).
Nearest ERA5-Land/ERA5 cells use grid.py (convention verified on real files).
"""

import csv
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pyproj
import shapely
import shapely.geometry as sgeom
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from elevation.acquire import tile_key, tiles_covering_bbox  # noqa: E402
from pipeline.coordinates import haversine_km  # noqa: E402
from spatial_proxy.matching import index_datameet_features_by_vct_code  # noqa: E402
from stage4_spatial_generalization import criteria, grid  # noqa: E402

REPO_ROOT = _RESEARCH_DIR.parent
RAW = REPO_ROOT / "data" / "raw"
SOURCES = {
    "lgd_pri_local_bodies": RAW / "lgd" / "pri_local_bodies.22Sep2026.csv",
    "lgd_villages_by_blocks": RAW / "lgd" / "villages_by_blocks.31Jul2026.csv",
    "lgd_villages": RAW / "lgd" / "villages.31Jul2026.csv",
    "datameet_ka_geojson": RAW / "datameet" / "ka.geojson",
    "datameet_provenance_manifest": RAW / "datameet" / "provenance_manifest.json",
    "glo30_tile_list": RAW / "elevation" / "tileList.txt",
    "yelandur_era5_linkage": _RESEARCH_DIR / "era5_linkage" / "yelandur_era5_linkage.json",
    "yelandur_spatial_proxy": _RESEARCH_DIR / "spatial_proxy" / "yelandur_spatial_proxy.json",
}
LOCAL_DEM_TILES = sorted((RAW / "elevation").glob("Copernicus_DSM_COG_10_*_DEM.tif"))
OUT_DIR = Path(__file__).resolve().parent
RESULTS_PATH = OUT_DIR / "feasibility_audit.json"
TALUK_CSV_PATH = OUT_DIR / "taluka_panchayat_audit.csv"

STATE = "Karnataka"
_to_utm = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True).transform
_to_wgs = pyproj.Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True).transform


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------

def load_gp_hierarchy(path: Path) -> dict[str, dict]:
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8")) if r["State Name"].strip() == STATE]
    by_code = {r["Localbody Code"]: r for r in rows}
    gps = {}
    for r in rows:
        if r["Localbody Type Name"] != "Gram Panchayat":
            continue
        tp = by_code.get(r["Parent Localbody Code"])
        zp = by_code.get(tp["Parent Localbody Code"]) if tp else None
        if not tp or tp["Localbody Type Name"] != "Taluka Panchayat" or not zp or zp["Localbody Type Name"] != "Zila Panchayat":
            raise RuntimeError(f"STOP: GP {r['Localbody Code']} does not chain GP->Taluka P.->Zila P. in LGD")
        gps[r["Localbody Code"]] = {
            "gp_code": r["Localbody Code"], "gp_name": r["Localbody Name (In English)"],
            "tp_code": tp["Localbody Code"], "tp_name": tp["Localbody Name (In English)"],
            "zp_code": zp["Localbody Code"], "zp_name": zp["Localbody Name (In English)"],
        }
    return gps


def load_gp_villages(vbb_path: Path, villages_path: Path, gp_codes: set[str]) -> tuple[dict, dict]:
    census2001 = {r["Village Code"]: r["Census 2001 Code"].strip()
                  for r in csv.DictReader(open(villages_path, encoding="utf-8"))
                  if r["State Name(In English)"].strip() == STATE}
    links = [r for r in csv.DictReader(open(vbb_path, encoding="utf-8"))
             if r["State Name (In English)"].strip() == STATE and r["Local Body Code"] in gp_codes]
    gps_per_village = Counter(r["Village Code"] for r in links)
    by_gp = defaultdict(list)
    for r in links:
        code = r["Village Code"]
        by_gp[r["Local Body Code"]].append({
            "village_code": code, "village_name": r["Village Name (In English)"],
            "census_2001_code": census2001.get(code, ""),
            "shared_with_other_gp": gps_per_village[code] > 1,
        })
    stats = {"village_gp_links": len(links), "villages_linked_to_gps": len(gps_per_village),
             "villages_linked_to_more_than_one_gp": sum(1 for c in gps_per_village.values() if c > 1)}
    return by_gp, stats


def load_datameet(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["features"]


def load_tile_list(path: Path) -> set[str]:
    return {line.strip() for line in open(path, encoding="utf-8") if line.strip()}


# ---------------------------------------------------------------------
# Per-GP proxy + linkage
# ---------------------------------------------------------------------

def gp_proxy_record(gp: dict, villages: list[dict], by_vct: dict[str, list[dict]]) -> dict:
    rec = dict(gp)
    rec["n_villages"] = len(villages)
    rec["has_shared_village"] = any(v["shared_with_other_gp"] for v in villages)
    geoms, n_matched, invalid = [], 0, 0
    for v in villages:
        c = v["census_2001_code"]
        key = c.zfill(8) if c and c != "0" else ""
        feats = by_vct.get(key, []) if key else []
        if len(feats) == 1:
            n_matched += 1
            g = sgeom.shape(feats[0]["geometry"])
            if not g.is_valid:
                invalid += 1
            geoms.append(g)
    rec["n_matched"] = n_matched
    rec["n_invalid_source_geometries"] = invalid
    if not villages:
        rec["status"] = "NO_LGD_VILLAGES"
    elif n_matched == 0:
        rec["status"] = "UNAVAILABLE"
    elif invalid:
        rec["status"] = "INVALID_GEOMETRY"
    elif n_matched < len(villages):
        rec["status"] = "PARTIAL"
    else:
        rec["status"] = "COMPLETE"

    if rec["status"] == "COMPLETE":
        union = unary_union(geoms)
        if not union.is_valid:
            rec["status"] = "INVALID_GEOMETRY"
            return rec
        utm = transform(_to_utm, union)
        c = transform(_to_wgs, utm.centroid)
        rec.update({
            "centroid_lat": c.y, "centroid_lon": c.x, "area_km2": utm.area / 1e6,
            "bounds": list(union.bounds),
            "era5_land_cell": list(grid.era5_land_cell(c.y, c.x)),
            "era5_box": list(grid.enclosing_era5_box(grid.era5_land_cell(c.y, c.x))),
            "_geometry": union,
        })
    return rec


# ---------------------------------------------------------------------
# Elevation (only where GLO-30 tiles are already on disk)
# ---------------------------------------------------------------------

def full_tile_name(key: str) -> str:
    """'N11_00_E077_00' -> 'Copernicus_DSM_COG_10_N11_00_E077_00_DEM' (tileList.txt / file naming)."""
    return f"Copernicus_DSM_COG_10_{key}_DEM"


def tiles_for_bounds(minx: float, miny: float, maxx: float, maxy: float) -> list[str]:
    return [full_tile_name(k) for k in tiles_covering_bbox(minx, miny, maxx, maxy)]


def local_tile_names() -> set[str]:
    return {p.name.replace(".tif", "") for p in LOCAL_DEM_TILES}


def attach_local_elevation(records: list[dict]) -> int:
    """GLO-30 zonal mean/min/max for COMPLETE GPs whose geometry lies
    entirely inside tiles already on disk. Returns how many got stats."""
    from elevation.extract import compute_zonal_stats, load_mosaic

    local = local_tile_names()
    todo = [r for r in records if r["status"] == "COMPLETE"
            and set(tiles_for_bounds(*r["bounds"])) <= local]
    if not todo:
        return 0
    arr, tf, _crs = load_mosaic(LOCAL_DEM_TILES)
    for r in todo:
        s = compute_zonal_stats(sgeom.mapping(r["_geometry"]), arr, tf)
        r["elevation_mean_m"], r["elevation_min_m"], r["elevation_max_m"] = s["mean_m"], s["min_m"], s["max_m"]
    return len(todo)


# ---------------------------------------------------------------------
# Candidate (Taluka Panchayat) summaries
# ---------------------------------------------------------------------

def summarize_candidate(tp_code: str, recs: list[dict], yelandur_cells: set, yelandur_centroid: tuple,
                        public_tiles: set[str], cell_in_ka: dict, cell_tp_count: dict) -> dict:
    complete = [r for r in recs if r["status"] == "COMPLETE"]
    status_counts = Counter(r["status"] for r in recs)
    n = len(recs)
    cells = Counter(tuple(r["era5_land_cell"]) for r in complete)
    new_cells = {c for c in cells if c not in yelandur_cells}
    adjacent = {c for c in new_cells
                if any(grid.chebyshev_cells(c, y) <= criteria.ADJACENT_CELL_RADIUS for y in yelandur_cells)}
    centroid = (statistics.fmean(r["centroid_lat"] for r in complete),
                statistics.fmean(r["centroid_lon"] for r in complete)) if complete else None
    dist = haversine_km(*centroid, *yelandur_centroid) if centroid else None

    tiles, tiles_public, tiles_local = [], None, None
    if complete:
        minx = min(r["bounds"][0] for r in complete); miny = min(r["bounds"][1] for r in complete)
        maxx = max(r["bounds"][2] for r in complete); maxy = max(r["bounds"][3] for r in complete)
        tiles = tiles_for_bounds(minx, miny, maxx, maxy)
        tiles_public = all(t in public_tiles for t in tiles)
        tiles_local = set(tiles) <= local_tile_names()
    elev = [r["elevation_mean_m"] for r in complete if r.get("elevation_mean_m") is not None]
    elevation = ({"status": "COMPUTED_FROM_LOCAL_GLO30", "gp_mean_min_m": min(elev), "gp_mean_max_m": max(elev),
                  "gp_mean_spread_m": max(elev) - min(elev), "n_gps": len(elev)}
                 if complete and len(elev) == len(complete)
                 else {"status": "PENDING_TILE_DOWNLOAD" if complete else "NO_COMPLETE_GPS",
                       "n_gps_with_local_stats": len(elev)})

    per_cell = sorted(cells.values())
    outside = sorted(grid.cell_id(c) for c in new_cells if not cell_in_ka[c])
    shared_cells = sorted(grid.cell_id(c) for c in cells if cell_tp_count[c] > 1)
    shared_village_gps = sum(1 for r in complete if r["has_shared_village"])

    summary = {
        "tp_code": tp_code, "tp_name": recs[0]["tp_name"], "zp_code": recs[0]["zp_code"], "zp_name": recs[0]["zp_name"],
        "administrative": {"lgd_gps": n, "gps_with_lgd_villages": n - status_counts.get("NO_LGD_VILLAGES", 0)},
        "spatial_proxy": {
            "status_counts": dict(sorted(status_counts.items())),
            "complete_gps": len(complete),
            "complete_share": len(complete) / n if n else 0.0,
            "villages": sum(r["n_villages"] for r in recs),
            "villages_matched_exact_code": sum(r["n_matched"] for r in recs),
            "complete_gps_with_shared_village": shared_village_gps,
        },
        "elevation": {"glo30_tiles_required": tiles, "all_tiles_publicly_listed": tiles_public,
                      "all_tiles_on_disk": tiles_local, **elevation},
        "grid": {
            "era5_land_cells": len(cells),
            "new_era5_land_cells_vs_yelandur": len(new_cells),
            "new_cells_adjacent_to_yelandur_cells": len(adjacent),
            "cells_shared_with_other_taluka_panchayats": len(shared_cells),
            "new_cell_centres_outside_karnataka_village_polygons": outside,
            "distinct_era5_0p25_boxes": len({tuple(r["era5_box"]) for r in complete}),
            "complete_gps_per_cell": {"min": per_cell[0], "median": statistics.median(per_cell), "max": per_cell[-1]}
            if per_cell else None,
            "cells_with_single_gp": sum(1 for v in per_cell if v == 1),
        },
        "centroid": {"lat": centroid[0], "lon": centroid[1]} if centroid else None,
        "distance_to_yelandur_km": dist,
    }
    summary["decision"], summary["reasons"] = decide(summary, tp_code)
    return summary


def decide(s: dict, tp_code: str) -> tuple[str, list[str]]:
    if tp_code == criteria.YELANDUR_TALUKA_PANCHAYAT_CODE:
        return "FROZEN_EXISTING", ["Yelandur is the frozen Phase 2D experiment; not a Stage 4 candidate."]
    sp, g = s["spatial_proxy"], s["grid"]
    fails = []
    if sp["complete_share"] < criteria.MIN_COMPLETE_GP_SHARE:
        fails.append(f"COMPLETE spatial-proxy share {sp['complete_share']:.2f} < {criteria.MIN_COMPLETE_GP_SHARE}")
    if g["new_era5_land_cells_vs_yelandur"] < criteria.MIN_NEW_CELL_GROUPS:
        fails.append(f"{g['new_era5_land_cells_vs_yelandur']} new ERA5-Land cells < {criteria.MIN_NEW_CELL_GROUPS}")
    d = s["distance_to_yelandur_km"]
    if d is None or d < criteria.MIN_DISTANCE_FROM_YELANDUR_KM:
        fails.append(f"distance to Yelandur {d if d is None else round(d, 1)} km < {criteria.MIN_DISTANCE_FROM_YELANDUR_KM} km")
    if fails:
        return "EXCLUDE", fails
    flags = []
    if g["new_cell_centres_outside_karnataka_village_polygons"]:
        flags.append(f"{len(g['new_cell_centres_outside_karnataka_village_polygons'])} new cell centre(s) outside "
                     "Karnataka village polygons (possible sea / other-state cell; ERA5-Land land-sea mask not checked)")
    if sp["complete_gps_with_shared_village"]:
        flags.append(f"{sp['complete_gps_with_shared_village']} COMPLETE GP(s) contain a village LGD maps to >1 GP")
    reasons = [f"{sp['complete_gps']}/{s['administrative']['lgd_gps']} GPs COMPLETE ({sp['complete_share']:.0%})",
               f"{g['new_era5_land_cells_vs_yelandur']} new ERA5-Land cells", f"{d:.0f} km from Yelandur"]
    return ("CONDITIONAL", reasons + flags) if flags else ("RECOMMEND_FOR_SHORTLIST", reasons)


# ---------------------------------------------------------------------
# Yelandur reproduction (provenance check against frozen artifacts)
# ---------------------------------------------------------------------

def yelandur_reproduction(records: list[dict]) -> dict:
    linkage = json.loads(SOURCES["yelandur_era5_linkage"].read_text(encoding="utf-8"))
    proxy = json.loads(SOURCES["yelandur_spatial_proxy"].read_text(encoding="utf-8"))
    mine = {r["gp_code"]: r for r in records if r["tp_code"] == criteria.YELANDUR_TALUKA_PANCHAYAT_CODE}
    frozen_status = {g["panchayat_lgd_code"]: g["geometry_status"] for g in proxy["panchayats"]}
    frozen_cell = {g["panchayat_lgd_code"]: (g["nearest_grid_latitude"], g["nearest_grid_longitude"])
                   for g in linkage["panchayats"] if g["coverage_status"] == "COMPLETE"}
    frozen_centroid = {g["panchayat_lgd_code"]: g["centroid_wgs84"] for g in proxy["panchayats"]
                       if g["geometry_status"] == "COMPLETE"}
    status_match = {c: mine[c]["status"] == s for c, s in frozen_status.items()}
    cell_match = {c: tuple(round(x, 6) for x in mine[c]["era5_land_cell"]) == tuple(round(x, 6) for x in cell)
                  for c, cell in frozen_cell.items()}
    centroid_diff = max(max(abs(mine[c]["centroid_lat"] - v["lat"]), abs(mine[c]["centroid_lon"] - v["lon"]))
                        for c, v in frozen_centroid.items())
    out = {
        "gp_codes_match": set(mine) == set(frozen_status),
        "status_matches": sum(status_match.values()), "status_compared": len(status_match),
        "nearest_cell_matches": sum(cell_match.values()), "nearest_cell_compared": len(cell_match),
        "max_centroid_difference_deg": centroid_diff,
        "distinct_complete_cells": len({tuple(r["era5_land_cell"]) for r in mine.values() if r["status"] == "COMPLETE"}),
    }
    out["reproduced"] = (out["gp_codes_match"] and out["status_matches"] == out["status_compared"]
                         and out["nearest_cell_matches"] == out["nearest_cell_compared"]
                         and centroid_diff < 1e-9 and out["distinct_complete_cells"] == 4)
    if not out["reproduced"]:
        raise RuntimeError(f"STOP: audit method does not reproduce frozen Yelandur artifacts: {out}")
    return out


# ---------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------

def build_gp_records() -> tuple[list[dict], list[dict], dict]:
    """Per-GP proxy/linkage records for all of Karnataka (no elevation),
    plus the DataMeet features and village-link statistics."""
    gps = load_gp_hierarchy(SOURCES["lgd_pri_local_bodies"])
    villages_by_gp, village_stats = load_gp_villages(SOURCES["lgd_villages_by_blocks"], SOURCES["lgd_villages"], set(gps))
    features = load_datameet(SOURCES["datameet_ka_geojson"])
    by_vct = index_datameet_features_by_vct_code(features)
    records = [gp_proxy_record(gp, villages_by_gp.get(code, []), by_vct) for code, gp in sorted(gps.items())]
    return records, features, village_stats


def run() -> dict:
    records, features, village_stats = build_gp_records()
    public_tiles = load_tile_list(SOURCES["glo30_tile_list"])
    n_elev = attach_local_elevation(records)
    repro = yelandur_reproduction(records)

    complete = [r for r in records if r["status"] == "COMPLETE"]
    yel = [r for r in complete if r["tp_code"] == criteria.YELANDUR_TALUKA_PANCHAYAT_CODE]
    yelandur_cells = {tuple(r["era5_land_cell"]) for r in yel}
    yelandur_centroid = (statistics.fmean(r["centroid_lat"] for r in yel), statistics.fmean(r["centroid_lon"] for r in yel))

    all_cells = {tuple(r["era5_land_cell"]) for r in complete}
    tree = STRtree([sgeom.shape(f["geometry"]) for f in features])
    cell_in_ka = {c: len(tree.query(sgeom.Point(c[1], c[0]), predicate="intersects")) > 0 for c in all_cells}
    cell_tps = defaultdict(set)
    for r in complete:
        cell_tps[tuple(r["era5_land_cell"])].add(r["tp_code"])
    cell_tp_count = {c: len(v) for c, v in cell_tps.items()}

    by_tp = defaultdict(list)
    for r in records:
        by_tp[r["tp_code"]].append(r)
    candidates = [summarize_candidate(tp, recs, yelandur_cells, yelandur_centroid, public_tiles, cell_in_ka, cell_tp_count)
                  for tp, recs in sorted(by_tp.items())]

    decisions = Counter(c["decision"] for c in candidates)
    recommended = [c for c in candidates if c["decision"] == "RECOMMEND_FOR_SHORTLIST"]
    rec_cells = set()
    for r in complete:
        if r["tp_code"] in {c["tp_code"] for c in recommended} and tuple(r["era5_land_cell"]) not in yelandur_cells:
            rec_cells.add(tuple(r["era5_land_cell"]))

    zp = defaultdict(list)
    for c in candidates:
        zp[(c["zp_code"], c["zp_name"])].append(c)
    district_summary = []
    for (code, name), cs in sorted(zp.items(), key=lambda kv: kv[0][1]):
        ok = [c for c in cs if c["decision"] == "RECOMMEND_FOR_SHORTLIST"]
        best = max(ok, key=lambda c: (c["grid"]["new_era5_land_cells_vs_yelandur"], c["spatial_proxy"]["complete_share"]), default=None)
        district_summary.append({
            "zp_code": code, "zp_name": name, "taluka_panchayats": len(cs),
            "decisions": dict(Counter(c["decision"] for c in cs)),
            "complete_gps": sum(c["spatial_proxy"]["complete_gps"] for c in cs),
            "lgd_gps": sum(c["administrative"]["lgd_gps"] for c in cs),
            "distinct_new_cells": len({tuple(r["era5_land_cell"]) for r in complete if r["zp_code"] == code} - yelandur_cells),
            "best_recommended_candidate": None if best is None else {
                "tp_code": best["tp_code"], "tp_name": best["tp_name"],
                "new_cells": best["grid"]["new_era5_land_cells_vs_yelandur"],
                "complete_share": best["spatial_proxy"]["complete_share"],
                "distance_to_yelandur_km": best["distance_to_yelandur_km"]},
        })

    status_counts = Counter(r["status"] for r in records)
    return {
        "type": "Stage4SpatialGeneralizationFeasibilityAudit",
        "scope": "Offline feasibility audit only: no data downloaded, no dataset built, no model trained.",
        "target_framing": "Target remains the ERA5-Land reanalysis proxy — not observation. No observational validation is claimed.",
        "frozen": "The Yelandur 4-cell experiment and Stage 1/2/3A/3B artifacts are read-only inputs here.",
        "candidate_unit": "LGD Taluka Panchayat (same PRI tier as Yelandur, code 6132)",
        "criteria": {k: getattr(criteria, k) for k in ("MIN_COMPLETE_GP_SHARE", "MIN_NEW_CELL_GROUPS",
                                                       "MIN_DISTANCE_FROM_YELANDUR_KM", "ADJACENT_CELL_RADIUS")},
        "methods": {
            "spatial_proxy_matching": "exact code only: LGD Census-2001 code zero-padded to 8 == DataMeet V_CT_CODE; no name fallback, no fuzzy matching",
            "invalid_geometry": "never repaired; GP reported INVALID_GEOMETRY",
            "centroid": "unary_union of matched village polygons; centroid in EPSG:32643 (Yelandur method)",
            "era5_land_cell": "nearest 0.1 deg centre (grid.py; convention verified on real ERA5-Land files)",
            "cell_group": "distinct nearest ERA5-Land cell among COMPLETE GPs (Phase 2D definition)",
            "independence": "cells not used by Yelandur; distance of candidate centroid to Yelandur's; adjacency within 1 cell",
            "elevation": "GLO-30 zonal stats only where all required tiles are already on disk; else PENDING_TILE_DOWNLOAD",
        },
        "temporal_availability": {
            "statement": ("ERA5 (reanalysis-era5-single-levels) and ERA5-Land (reanalysis-era5-land) are global gridded "
                          "products; 2021-01-01..2023-12-31 hourly availability was verified by the 72/72 Phase 2D "
                          "monthly downloads for the Yelandur area. It was NOT re-verified per candidate region "
                          "(no download in this audit)."),
        },
        "provenance": {
            "source_sha256": {k: sha256(p) for k, p in SOURCES.items()},
            "source_paths": {k: p.resolve().relative_to(REPO_ROOT).as_posix() for k, p in SOURCES.items()},
            "datameet_manifest": json.loads(SOURCES["datameet_provenance_manifest"].read_text(encoding="utf-8")),
            "local_glo30_tiles": [p.name for p in LOCAL_DEM_TILES],
        },
        "yelandur_reproduction_check": repro,
        "statewide": {
            "lgd_gram_panchayats": len(records),
            "lgd_taluka_panchayats": len(by_tp),
            "lgd_zila_panchayats": len(zp),
            "gp_status_counts": dict(sorted(status_counts.items())),
            **village_stats,
            "datameet_features": len(features),
            "datameet_features_without_v_ct_code": sum(1 for f in features if not (f["properties"].get("V_CT_CODE") or "").strip()),
            "complete_gps": len(complete),
            "distinct_era5_land_cells_with_complete_gps": len(all_cells),
            "cells_spanning_multiple_taluka_panchayats": sum(1 for v in cell_tp_count.values() if v > 1),
            "cell_centres_outside_karnataka_village_polygons": sum(1 for v in cell_in_ka.values() if not v),
            "complete_gps_with_local_glo30_stats": n_elev,
            "yelandur_cells": sorted(grid.cell_id(c) for c in yelandur_cells),
        },
        "decision_counts": dict(sorted(decisions.items())),
        "recommended_shortlist_new_cells_total": len(rec_cells),
        "district_summary": district_summary,
        "candidates": candidates,
    }


def write_outputs(result: dict) -> None:
    RESULTS_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    cols = ["tp_code", "tp_name", "zp_name", "decision", "lgd_gps", "complete_gps", "complete_share",
            "era5_land_cells", "new_cells", "adjacent_to_yelandur", "cells_single_gp", "distance_to_yelandur_km",
            "elevation_status", "gp_mean_elev_spread_m", "outside_ka_new_cells", "reasons"]
    with open(TALUK_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for c in result["candidates"]:
            w.writerow([c["tp_code"], c["tp_name"], c["zp_name"], c["decision"], c["administrative"]["lgd_gps"],
                        c["spatial_proxy"]["complete_gps"], round(c["spatial_proxy"]["complete_share"], 4),
                        c["grid"]["era5_land_cells"], c["grid"]["new_era5_land_cells_vs_yelandur"],
                        c["grid"]["new_cells_adjacent_to_yelandur_cells"], c["grid"]["cells_with_single_gp"],
                        None if c["distance_to_yelandur_km"] is None else round(c["distance_to_yelandur_km"], 1),
                        c["elevation"]["status"], None if "gp_mean_spread_m" not in c["elevation"]
                        else round(c["elevation"]["gp_mean_spread_m"], 1),
                        len(c["grid"]["new_cell_centres_outside_karnataka_village_polygons"]), " | ".join(c["reasons"])])


if __name__ == "__main__":
    res = run()
    write_outputs(res)
    print(f"Wrote {RESULTS_PATH} and {TALUK_CSV_PATH}")
    print("decisions:", res["decision_counts"], "| Yelandur reproduced:", res["yelandur_reproduction_check"]["reproduced"])
