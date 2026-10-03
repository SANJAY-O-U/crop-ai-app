"""
Stage 5 station matching (metadata only; no observation values used).

Applies criteria5 mechanically to every ISD station in a box around
Karnataka and writes station_inventory.csv and station_matching.csv.
"""

import json
import sys
from pathlib import Path

import pandas as pd
import shapely.geometry as sgeom
from shapely.ops import unary_union

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from pipeline.coordinates import haversine_km  # noqa: E402
from stage4_spatial_generalization import audit, grid  # noqa: E402
from stage5_observational_validation import criteria5  # noqa: E402

MODULE = Path(__file__).resolve().parent
RESULTS = MODULE / "results"
ISD_HISTORY = audit.REPO_ROOT / "data" / "raw" / "observations" / "isd" / "isd-history.csv"
DATASET_MANIFEST = _RESEARCH_DIR / "stage4_spatial_generalization" / "stage4_dataset_manifest.json"
PHASE2D_LINKAGE = _RESEARCH_DIR / "era5_linkage" / "yelandur_era5_linkage.json"
KARNATAKA_BOX = {"lat": (11.4, 18.6), "lon": (73.9, 78.8)}


def isd_candidates() -> pd.DataFrame:
    h = pd.read_csv(ISD_HISTORY, dtype=str)
    h = h[h["CTRY"] == "IN"].copy()
    for c in ("LAT", "LON", "ELEV(M)"):
        h[c] = pd.to_numeric(h[c], errors="coerce")
    h = h[h["LAT"].between(*KARNATAKA_BOX["lat"]) & h["LON"].between(*KARNATAKA_BOX["lon"])]
    b, e = criteria5.REQUIRE_METADATA_COVERAGE
    h["covers_eval_year"] = (h["BEGIN"] <= b) & (h["END"] >= e)
    h["station_id"] = h["USAF"] + "-" + h["WBAN"]
    return h.rename(columns={"STATION NAME": "station_name", "LAT": "latitude", "LON": "longitude",
                             "ELEV(M)": "elevation_m", "ICAO": "icao", "BEGIN": "begin", "END": "end"})


def selected_geography() -> dict:
    m = json.loads(DATASET_MANIFEST.read_text(encoding="utf-8"))
    included = {g["gp_code"]: g for g in m["gps"]}
    records, _, _ = audit.build_gp_records()
    areas = {}
    names = {a["tp_code"]: a for a in m["dataset_files"]}
    for r in records:
        if r["gp_code"] not in included:
            continue
        a = areas.setdefault(r["tp_code"], {"tp_code": r["tp_code"], "tp_name": names[r["tp_code"]]["tp_name"],
                                            "district": names[r["tp_code"]]["zp_name"],
                                            "region": names[r["tp_code"]]["geographic_regime"],
                                            "cells": set(names[r["tp_code"]]["cells"]), "gps": []})
        a["gps"].append({"gp_code": r["gp_code"], "gp_name": r["gp_name"], "geometry": r["_geometry"],
                         "cell": grid.cell_id(tuple(r["era5_land_cell"])), "centroid": (r["centroid_lat"], r["centroid_lon"]),
                         "elevation_mean_m": included[r["gp_code"]]["elevation_mean_m"]})
    for a in areas.values():
        a["union"] = unary_union([g["geometry"] for g in a["gps"]])
    return areas


def match_station(st: pd.Series, areas: dict, yelandur_cells: set) -> dict:
    lat, lon = float(st["latitude"]), float(st["longitude"])
    cell = grid.era5_land_cell(lat, lon)
    cid = grid.cell_id(cell)
    pt = sgeom.Point(lon, lat)
    out = {"station_id": st["station_id"], "station_name": st["station_name"], "latitude": lat, "longitude": lon,
           "elevation_m": st["elevation_m"], "nearest_era5_land_cell": cid, "match_set": "EXCLUDED",
           "tp_code": None, "tp_name": None, "district": None, "region": None, "gp_code": None, "gp_name": None,
           "model_target_cell": None, "station_to_target_cell_km": None, "station_to_gp_centroid_km": None,
           "gp_elevation_mean_m": None, "station_minus_gp_elevation_m": None, "reason": ""}
    for a in areas.values():
        if a["union"].contains(pt) and cid in a["cells"]:
            gp = next(g for g in a["gps"] if g["geometry"].contains(pt))
            return _fill(out, "PRIMARY", a, gp, lat, lon, "inside included Panchayat polygon and nearest cell is a target cell")
    best = None
    for a in areas.values():
        sep = min(grid.chebyshev_cells(cell, grid.parse_cell_id(c)) for c in a["cells"])
        if sep <= criteria5.ADJACENT_CELLS and (best is None or sep < best[0]):
            best = (sep, a)
    if best is not None:
        a = best[1]
        gp = min(a["gps"], key=lambda g: haversine_km(lat, lon, *g["centroid"]))
        return _fill(out, "NEARBY_DIAGNOSTIC", a, gp, lat, lon,
                     f"nearest cell {'is' if best[0] == 0 else 'is adjacent to'} a target cell of {a['tp_name']}; outside Panchayat polygons")
    out["reason"] = ("nearest cell is a Yelandur (frozen reference) cell" if cid in yelandur_cells
                     else "not within 1 cell of any selected-area target cell")
    return out


def _fill(out, kind, a, gp, lat, lon, reason):
    tc = grid.parse_cell_id(gp["cell"])
    out.update({"match_set": kind, "tp_code": a["tp_code"], "tp_name": a["tp_name"], "district": a["district"],
                "region": a["region"], "gp_code": gp["gp_code"], "gp_name": gp["gp_name"], "model_target_cell": gp["cell"],
                "station_to_target_cell_km": haversine_km(lat, lon, *tc),
                "station_to_gp_centroid_km": haversine_km(lat, lon, *gp["centroid"]),
                "gp_elevation_mean_m": gp["elevation_mean_m"], "reason": reason})
    if out["elevation_m"] is not None and not pd.isna(out["elevation_m"]):
        out["station_minus_gp_elevation_m"] = float(out["elevation_m"]) - gp["elevation_mean_m"]
    return out


def run() -> pd.DataFrame:
    RESULTS.mkdir(parents=True, exist_ok=True)
    inv = isd_candidates()
    inv.to_csv(RESULTS / "station_inventory.csv", index=False)
    areas = selected_geography()
    link = json.loads(PHASE2D_LINKAGE.read_text(encoding="utf-8"))
    yel_cells = {grid.cell_id((g["nearest_grid_latitude"], g["nearest_grid_longitude"]))
                 for g in link["panchayats"] if g["nearest_grid_latitude"] is not None}
    rows = []
    for _, st in inv.sort_values("station_id").iterrows():
        m = match_station(st, areas, yel_cells)
        m["covers_eval_year"] = bool(st["covers_eval_year"])
        if m["match_set"] != "EXCLUDED" and not st["covers_eval_year"]:
            m["match_set"], m["reason"] = "EXCLUDED", "ISD metadata does not cover the 2023 evaluation year; " + m["reason"]
        rows.append(m)
    df = pd.DataFrame(rows)
    df.to_csv(RESULTS / "station_matching.csv", index=False)
    return df


if __name__ == "__main__":
    d = run()
    print(d["match_set"].value_counts().to_dict())
    print(d[d["match_set"] != "EXCLUDED"][["station_id", "station_name", "match_set", "tp_name", "gp_name",
                                            "station_to_target_cell_km", "station_to_gp_centroid_km",
                                            "station_minus_gp_elevation_m"]].to_string())
