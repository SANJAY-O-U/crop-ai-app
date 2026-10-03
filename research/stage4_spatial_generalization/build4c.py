"""
Stage 4C: build the expanded 11-area multi-GP dataset from the Stage 4
acquisition, with integrity checks. Writes:

    data/training/stage4/<taluka_panchayat_code>.parquet   (gitignored; one file per area)
    research/stage4_spatial_generalization/stage4_dataset_manifest.json
    research/stage4_spatial_generalization/stage4c_acquisition_record.json

The frozen Phase 2D Yelandur dataset and the Stage 4A/4B design manifest are
read-only. Reuses Phase 2D logic unchanged: multi_gp.build._point_series
(nearest-point extraction, ERA5-Land de-accumulation over the continuous
2021-2023 series, unit conversion via pipeline.normalize/units),
multi_gp.pairing (bilinear + nearest ERA5 pairing), multi_gp.splits
(temporal periods), era5_linkage.linkage (intersecting cells),
elevation.extract (GLO-30 zonal stats).

Documented correction (hard data-integrity failure, see CORRECTIONS): a
selected GP whose nearest ERA5-Land cell is NOT land in ERA5-Land (missing
value in the land/sea probe) is excluded as NON_LAND_TARGET_CELL. It is never
re-assigned to another cell. No other part of the frozen design changes.
"""

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import shapely.geometry as sgeom

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from era5_linkage import linkage  # noqa: E402
from multi_gp import acquire as p2d  # noqa: E402
from multi_gp import pairing, splits  # noqa: E402
from multi_gp.build import IST_OFFSET, SOURCE_NOTE, VARIABLES_OUT, _point_series  # noqa: E402
from pipeline.coordinates import haversine_km  # noqa: E402
from pipeline.normalize import ERA5_LAND_SHORT_NAME_TO_CANONICAL  # noqa: E402
from stage4_spatial_generalization import acquire4c, audit, grid  # noqa: E402

OUT_DIR = audit.REPO_ROOT / "data" / "training" / "stage4"
DATASET_MANIFEST = Path(__file__).resolve().parent / "stage4_dataset_manifest.json"
ACQ_RECORD = Path(__file__).resolve().parent / "stage4c_acquisition_record.json"
TARGET_DEFINITION = "era5_land_0.1deg_nearest_cell_to_gp_centroid"
IS_LAND_RULE = "cell is ERA5-Land land iff its 2m_temperature value is not missing (NaN) in the land/sea probe"

COLUMNS = [
    "panchayat_lgd_code", "gp_name", "gp_status",
    "taluka_panchayat_lgd_code", "taluka_panchayat_name", "zila_panchayat_lgd_code", "district_name",
    "geographic_regime", "timestamp_utc", "local_date_ist", "variable",
    "target_value", "target_unit", "target_definition", "target_missing_reason", "target_rainfall_clamped",
    "cell_group_id", "target_cell_latitude", "target_cell_longitude", "cell_group_complete_gp_count",
    "coarse_bilinear_value", "coarse_nearest_value", "coarse_unit",
    "coarse_nearest_latitude", "coarse_nearest_longitude", "coarse_nearest_distance_km",
    "centroid_latitude", "centroid_longitude", "centroid_to_cell_km", "intersecting_cell_count",
    "elevation_mean_m", "elevation_min_m", "elevation_max_m", "elevation_range_m", "elevation_std_m",
    "temporal_period", "taluka_holdout_fold", "district_holdout_fold", "regional_holdout_fold", "cell_diagnostic_fold",
    "target_source_file", "target_source_sha256", "coarse_source_file", "coarse_source_sha256", "source_note",
]


_STR = pa.string()
_F = pa.float64()
SCHEMA = pa.schema([
    ("panchayat_lgd_code", _STR), ("gp_name", _STR), ("gp_status", _STR),
    ("taluka_panchayat_lgd_code", _STR), ("taluka_panchayat_name", _STR), ("zila_panchayat_lgd_code", _STR),
    ("district_name", _STR), ("geographic_regime", _STR), ("timestamp_utc", pa.timestamp("ns", tz="UTC")),
    ("local_date_ist", _STR), ("variable", _STR),
    ("target_value", _F), ("target_unit", _STR), ("target_definition", _STR), ("target_missing_reason", _STR),
    ("target_rainfall_clamped", pa.bool_()),
    ("cell_group_id", _STR), ("target_cell_latitude", _F), ("target_cell_longitude", _F),
    ("cell_group_complete_gp_count", pa.int64()),
    ("coarse_bilinear_value", _F), ("coarse_nearest_value", _F), ("coarse_unit", _STR),
    ("coarse_nearest_latitude", _F), ("coarse_nearest_longitude", _F), ("coarse_nearest_distance_km", _F),
    ("centroid_latitude", _F), ("centroid_longitude", _F), ("centroid_to_cell_km", _F),
    ("intersecting_cell_count", pa.int64()),
    ("elevation_mean_m", _F), ("elevation_min_m", _F), ("elevation_max_m", _F), ("elevation_range_m", _F),
    ("elevation_std_m", _F),
    ("temporal_period", _STR), ("taluka_holdout_fold", _STR), ("district_holdout_fold", _STR),
    ("regional_holdout_fold", _STR), ("cell_diagnostic_fold", _STR),
    ("target_source_file", _STR), ("target_source_sha256", _STR), ("coarse_source_file", _STR),
    ("coarse_source_sha256", _STR), ("source_note", _STR),
])
assert [f.name for f in SCHEMA] == COLUMNS


def _sha(path: Path) -> str:
    return audit.sha256(path)


def _rel(path: Path) -> str:
    p = Path(path).resolve()
    try:
        return p.relative_to(audit.REPO_ROOT).as_posix()
    except ValueError:  # e.g. a rebuild into a temporary directory
        return p.as_posix()


# ---------------------------------------------------------------------
# Land/sea
# ---------------------------------------------------------------------

def land_status(cell_ids: list[str]) -> dict[str, bool]:
    import xarray as xr

    with xr.open_dataset(acquire4c.LAND_SEA_PROBE) as ds:
        t = ds["t2m"].isel(valid_time=0)
        lats, lons = ds["latitude"].values, ds["longitude"].values
        out = {}
        for cid in cell_ids:
            la, lo = grid.parse_cell_id(cid)
            i, j = np.flatnonzero(np.isclose(lats, la)), np.flatnonzero(np.isclose(lons, lo))
            if len(i) != 1 or len(j) != 1:
                raise ValueError(f"{cid} not in land/sea probe grid")
            out[cid] = bool(np.isfinite(float(t.values[i[0], j[0]])))
    return out


# ---------------------------------------------------------------------
# Weather: load the 36 monthly combined files, keep only needed points
# ---------------------------------------------------------------------

def _file_index(coords: np.ndarray, value: float) -> int:
    idx = np.flatnonzero(np.isclose(coords, value, atol=1e-6))
    if len(idx) != 1:
        raise ValueError(f"{value} not found exactly once in grid")
    return int(idx[0])


def load_weather(path_fn, points: list[tuple[float, float]] | None):
    """Concatenates all 36 months, subset to `points` (lat, lon) when given
    (otherwise lat/lon ranges needed are kept whole). Checks hours per month,
    identical grid every month, strictly increasing time. Returns the
    canonical-name dataset, the full grid of month 1, and per-month provenance."""
    import xarray as xr

    parts, prov, full_grid = [], {}, None
    for y, m in p2d.window_months():
        path = path_fn(y, m)
        if not path.exists():
            raise FileNotFoundError(f"missing {path}")
        ds = p2d.open_monthly(path)
        lats, lons = ds["latitude"].values, ds["longitude"].values
        if full_grid is None:
            full_grid = (lats.copy(), lons.copy())
        elif not (np.array_equal(lats, full_grid[0]) and np.array_equal(lons, full_grid[1])):
            raise ValueError(f"{path.name}: grid differs from month 1")
        n_expected = len(p2d.month_days(y, m)) * 24
        if ds.sizes["valid_time"] != n_expected:
            raise ValueError(f"{path.name}: {ds.sizes['valid_time']} hours, expected {n_expected}")
        if points is not None:
            li = sorted({_file_index(lats, p[0]) for p in points})
            lj = sorted({_file_index(lons, p[1]) for p in points})
            ds = ds.isel(latitude=li, longitude=lj)
        members = p2d.member_paths(path)
        hashes = [_sha(p) for p in members]
        side = acquire4c.sidecar(path)
        rec = json.loads(side.read_text(encoding="utf-8")) if side.exists() else {}
        prov[f"{y}-{m:02d}"] = {
            "files": [_rel(p) for p in members], "sha256": hashes,
            "combined_sha256": hashlib.sha256("".join(hashes).encode()).hexdigest(),
            "request_id": rec.get("request_id"), "request_area_nwse": rec.get("request", {}).get("area"),
            "variables": rec.get("request", {}).get("variable"), "hours": n_expected,
            "dims": {"valid_time": n_expected, "latitude": len(full_grid[0]), "longitude": len(full_grid[1])},
        }
        parts.append(ds.drop_vars([v for v in ("expver", "number") if v in ds.variables]))
    combined = xr.concat(parts, dim="valid_time")
    t = combined.indexes["valid_time"]
    if not t.is_monotonic_increasing or t.has_duplicates:
        raise ValueError("time axis not strictly increasing")
    rename = {k: v for k, v in ERA5_LAND_SHORT_NAME_TO_CANONICAL.items() if k in combined.data_vars}
    rename["valid_time"] = "time"
    return combined.rename(rename), full_grid, prov


def series_for(dataset, cell: tuple[float, float], deaccumulate: bool):
    lat = float(dataset["latitude"].values[_file_index(dataset["latitude"].values, cell[0])])
    lon = float(dataset["longitude"].values[_file_index(dataset["longitude"].values, cell[1])])
    return _point_series(dataset, lat, lon, deaccumulate=deaccumulate)


# ---------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------

def gp_elevation(gps: list[dict], tile_names: list[str]) -> dict[str, dict]:
    from elevation.extract import compute_zonal_stats, load_mosaic

    paths = [audit.RAW / "elevation" / f"{t}.tif" for t in tile_names]
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError(f"GLO-30 tiles missing: {missing}")
    arr, tf, _ = load_mosaic(paths)
    return {g["gp_code"]: compute_zonal_stats(sgeom.mapping(g["_geometry"]), arr, tf) for g in gps}


def build(tp_codes: list[str] | None = None, out_dir: Path = OUT_DIR, write_manifests: bool = True) -> dict:
    design = acquire4c.load_design()
    selected = [e for e in design["selected"] if tp_codes is None or e["tp_code"] in tp_codes]
    fold_design = design["fold_design"]
    diag_fold_of_cell = {cid: f["fold_id"] for f in fold_design["cell_group_diagnostic"]["folds"] for cid in f["test_cells"]}

    # --- identity + geometry, checked against the frozen design ---
    records, _, _ = audit.build_gp_records()
    by_tp = defaultdict(list)
    for r in records:
        by_tp[r["tp_code"]].append(r)
    all_expected = sorted({c for e in design["selected"] for c in e["expected_era5_land_cells"]})
    is_land = land_status(all_expected)

    included, excluded, corrections = {}, [], []
    for e in selected:
        frozen = {g["gp_code"]: g["era5_land_cell"] for g in e["spatial_proxy"]["complete_gps"]}
        recs = sorted(by_tp[e["tp_code"]], key=lambda r: r["gp_code"])
        complete_now = {r["gp_code"]: grid.cell_id(tuple(r["era5_land_cell"])) for r in recs if r["status"] == "COMPLETE"}
        if complete_now != frozen:
            raise RuntimeError(f"STOP: {e['tp_name']} COMPLETE GPs/cells differ from the frozen design manifest")
        keep = []
        for r in recs:
            if r["status"] != "COMPLETE":
                excluded.append({"tp_code": e["tp_code"], "gp_code": r["gp_code"], "gp_name": r["gp_name"], "status": r["status"]})
                continue
            cid = grid.cell_id(tuple(r["era5_land_cell"]))
            if not is_land[cid]:
                excluded.append({"tp_code": e["tp_code"], "gp_code": r["gp_code"], "gp_name": r["gp_name"],
                                 "status": "NON_LAND_TARGET_CELL", "era5_land_cell": cid})
                corrections.append({"tp_code": e["tp_code"], "tp_name": e["tp_name"], "gp_code": r["gp_code"],
                                    "gp_name": r["gp_name"], "era5_land_cell": cid,
                                    "correction": "excluded: nearest ERA5-Land cell is not land (missing value); "
                                                  "not re-assigned to another cell"})
                continue
            keep.append(r)
        included[e["tp_code"]] = keep

    # --- no overlap between areas (actual included cells) ---
    cells_by_tp = {tp: {tuple(r["era5_land_cell"]) for r in gps} for tp, gps in included.items()}
    tps = sorted(cells_by_tp)
    for i, a in enumerate(tps):
        for b in tps[i + 1:]:
            if cells_by_tp[a] & cells_by_tp[b]:
                raise RuntimeError(f"STOP: selected areas {a} and {b} share ERA5-Land cells")
    group_counts = Counter(tuple(r["era5_land_cell"]) for gps in included.values() for r in gps)
    target_cells = sorted(group_counts)

    # --- weather ---
    land, land_grid, land_prov = load_weather(acquire4c.era5_land_path, target_cells)
    coarse_full, coarse_grid, coarse_prov = load_weather(acquire4c.era5_path, None)
    c_lats, c_lons = coarse_grid
    pair = {}
    corner_points = set()
    for cell in target_cells:
        corners = pairing.bilinear_weights(c_lats, c_lons, cell[0], cell[1])
        nearest = pairing.nearest_coarse_point(c_lats, c_lons, cell[0], cell[1])
        pair[cell] = {"bilinear": corners, "nearest": nearest}
        corner_points |= {(a, b) for a, b, _ in corners} | {nearest[:2]}
    coarse = coarse_full.isel(latitude=sorted({_file_index(c_lats, p[0]) for p in corner_points}),
                              longitude=sorted({_file_index(c_lons, p[1]) for p in corner_points}))

    hours = pd.DatetimeIndex(pd.to_datetime(land["time"].values)).tz_localize("UTC")
    if not hours.equals(pd.DatetimeIndex(pd.to_datetime(coarse["time"].values)).tz_localize("UTC")):
        raise RuntimeError("STOP: ERA5 and ERA5-Land time axes differ")
    full_index = pd.MultiIndex.from_product([hours, VARIABLES_OUT], names=["timestamp", "variable"])

    target_series, clamped, max_clamp, units = {}, {}, 0.0, {}
    for cell in target_cells:
        df, cl, mx = series_for(land, cell, deaccumulate=True)
        target_series[cell] = df.set_index(["timestamp", "variable"])["value"].reindex(full_index)
        clamped[cell], max_clamp = cl, max(max_clamp, mx)
        units.update(dict(zip(df["variable"], df["unit"])))
    coarse_series, coarse_units = {}, {}
    for p in sorted(corner_points):
        df, _, _ = series_for(coarse, p, deaccumulate=False)
        coarse_series[p] = df.set_index(["timestamp", "variable"])["value"].reindex(full_index)
        coarse_units.update(dict(zip(df["variable"], df["unit"])))
    if units != coarse_units:
        raise RuntimeError(f"STOP: unit mismatch {units} vs {coarse_units}")

    # --- missing values: never filled; only the first de-accumulation hour may be missing ---
    first = hours[0]
    missing_report = {}
    for cell, s in target_series.items():
        miss = s[s.isna()]
        bad = [k for k in miss.index if not (k[1] == "rainfall_mm" and k[0] == first)]
        if bad:
            raise RuntimeError(f"STOP: unexpected missing target values at {grid.cell_id(cell)}: {bad[:3]}")
        missing_report[grid.cell_id(cell)] = len(miss)
    for p, s in coarse_series.items():
        if s.isna().any():
            raise RuntimeError(f"STOP: missing coarse values at ERA5 point {p}")

    # --- month-boundary continuity of rainfall ---
    month_starts = [h for h in hours if h.day == 1 and h.hour == 0 and h != first]
    boundary_missing = sum(int(pd.isna(s.loc[(h, "rainfall_mm")])) for s in target_series.values() for h in month_starts)
    if boundary_missing:
        raise RuntimeError(f"STOP: {boundary_missing} month-boundary rainfall values missing")

    # --- write one Parquet per area ---
    out_dir.mkdir(parents=True, exist_ok=True)
    ts_col = full_index.get_level_values("timestamp")
    var_col = full_index.get_level_values("variable")
    month_key = ts_col.strftime("%Y-%m")
    period = splits.temporal_period(pd.Series(ts_col)).to_numpy()
    local_date = (ts_col + IST_OFFSET).strftime("%Y-%m-%d")
    is_rain = np.asarray(var_col == "rainfall_mm")
    t_file = np.array([land_prov[k]["files"][0] for k in month_key])
    t_sha = np.array([land_prov[k]["combined_sha256"] for k in month_key])
    c_file = np.array(["|".join(coarse_prov[k]["files"]) for k in month_key])
    c_sha = np.array([coarse_prov[k]["combined_sha256"] for k in month_key])

    area_out, gp_out, row_total = [], [], 0
    for e in selected:
        gps = included[e["tp_code"]]
        elev = gp_elevation(gps, e["elevation"]["glo30_tiles_required"])
        path = out_dir / f"{e['tp_code']}.parquet"
        writer = None
        for r in gps:
            cell = tuple(r["era5_land_cell"])
            cid = grid.cell_id(cell)
            p = pair[cell]
            bil = sum(w * coarse_series[(a, b)].to_numpy() for a, b, w in p["bilinear"])
            nlat, nlon, ndist = p["nearest"]
            target = target_series[cell].to_numpy()
            inter = linkage.cells_intersecting_geometry(sgeom.mapping(r["_geometry"]), land_grid[0], land_grid[1])
            ev = elev[r["gp_code"]]
            n = len(full_index)
            frame = pd.DataFrame({
                "panchayat_lgd_code": r["gp_code"], "gp_name": r["gp_name"], "gp_status": "COMPLETE",
                "taluka_panchayat_lgd_code": e["tp_code"], "taluka_panchayat_name": e["tp_name"],
                "zila_panchayat_lgd_code": e["zp_code"], "district_name": e["zp_name"],
                "geographic_regime": e["geographic_regime"],
                "timestamp_utc": ts_col, "local_date_ist": local_date, "variable": np.asarray(var_col),
                "target_value": target, "target_unit": [units[v] for v in var_col],
                "target_definition": TARGET_DEFINITION,
                "target_missing_reason": np.where(np.isnan(target), "ERA5_LAND_DEACCUMULATION_FIRST_STEP", None),
                "target_rainfall_clamped": is_rain & np.asarray(ts_col.isin(list(clamped[cell]))),
                "cell_group_id": cid, "target_cell_latitude": cell[0], "target_cell_longitude": cell[1],
                "cell_group_complete_gp_count": group_counts[cell],
                "coarse_bilinear_value": bil, "coarse_nearest_value": coarse_series[(nlat, nlon)].to_numpy(),
                "coarse_unit": [coarse_units[v] for v in var_col],
                "coarse_nearest_latitude": nlat, "coarse_nearest_longitude": nlon, "coarse_nearest_distance_km": ndist,
                "centroid_latitude": r["centroid_lat"], "centroid_longitude": r["centroid_lon"],
                "centroid_to_cell_km": haversine_km(r["centroid_lat"], r["centroid_lon"], cell[0], cell[1]),
                "intersecting_cell_count": len(inter),
                "elevation_mean_m": ev["mean_m"], "elevation_min_m": ev["min_m"], "elevation_max_m": ev["max_m"],
                "elevation_range_m": ev["range_m"], "elevation_std_m": ev["std_m"],
                "temporal_period": period,
                "taluka_holdout_fold": e["fold_assignment"]["taluka_holdout"],
                "district_holdout_fold": e["fold_assignment"]["district_holdout"],
                "regional_holdout_fold": e["fold_assignment"]["regional_holdout"],
                "cell_diagnostic_fold": diag_fold_of_cell[cid],
                "target_source_file": t_file, "target_source_sha256": t_sha,
                "coarse_source_file": c_file, "coarse_source_sha256": c_sha,
                "source_note": SOURCE_NOTE,
            }, index=range(n))[COLUMNS]
            table = pa.Table.from_pandas(frame, schema=SCHEMA, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(path, SCHEMA)
            writer.write_table(table)
            gp_out.append({"tp_code": e["tp_code"], "gp_code": r["gp_code"], "gp_name": r["gp_name"],
                           "era5_land_cell": cid, "rows": n, "intersecting_cell_count": len(inter),
                           "elevation_mean_m": ev["mean_m"], "elevation_range_m": ev["range_m"],
                           "elevation_sample_count": ev["sample_count"]})
            row_total += n
        writer.close()
        area_out.append({
            "tp_code": e["tp_code"], "tp_name": e["tp_name"], "zp_name": e["zp_name"],
            "geographic_regime": e["geographic_regime"], "file": _rel(path), "sha256": _sha(path),
            "size_bytes": path.stat().st_size, "gps_included": len(gps), "rows": len(gps) * len(full_index),
            "cells": sorted(grid.cell_id(c) for c in cells_by_tp[e["tp_code"]]),
            "gps_per_cell": dict(sorted(Counter(grid.cell_id(tuple(r["era5_land_cell"])) for r in gps).items())),
            "fold_assignment": e["fold_assignment"],
        })

    result = {
        "areas": area_out, "gps": gp_out, "excluded_gps": excluded, "corrections": corrections,
        "row_total": row_total, "hours": len(hours), "variables": VARIABLES_OUT, "units": units,
        "time_range_utc": [str(hours[0]), str(hours[-1])],
        "months": sorted(land_prov), "land_prov": land_prov, "coarse_prov": coarse_prov,
        "land_grid": {"n_lat": len(land_grid[0]), "n_lon": len(land_grid[1])},
        "coarse_grid": {"n_lat": len(c_lats), "n_lon": len(c_lons)},
        "target_cells": [grid.cell_id(c) for c in target_cells],
        "is_land": is_land, "missing_target_by_cell": missing_report,
        "clamped_target_hours_by_cell": {grid.cell_id(c): len(v) for c, v in clamped.items()},
        "max_abs_clamped_step_mm": max_clamp,
        "month_boundary_rainfall_missing": boundary_missing,
        "pairing": {grid.cell_id(c): {"bilinear": [{"latitude": a, "longitude": b, "weight": w} for a, b, w in p["bilinear"]],
                                      "nearest": {"latitude": p["nearest"][0], "longitude": p["nearest"][1],
                                                  "distance_km": p["nearest"][2]}} for c, p in pair.items()},
    }
    if write_manifests:
        write_manifests_from(result, design)
    return result


def write_manifests_from(res: dict, design: dict) -> None:
    from stage4_spatial_generalization.design import PROTECTED_ARTIFACTS

    tiles = sorted({t for e in design["selected"] for t in e["elevation"]["glo30_tiles_required"]})
    tile_info = {t: {"file": _rel(audit.RAW / "elevation" / f"{t}.tif"), "sha256": _sha(audit.RAW / "elevation" / f"{t}.tif"),
                     "size_bytes": (audit.RAW / "elevation" / f"{t}.tif").stat().st_size} for t in tiles}
    probe = acquire4c.LAND_SEA_PROBE
    probe_side = json.loads(acquire4c.sidecar(probe).read_text(encoding="utf-8"))
    areas = acquire4c.combined_areas(design)
    storage = {
        "era5_land_raw_bytes": sum(sum(Path(audit.REPO_ROOT / f).stat().st_size for f in v["files"]) for v in res["land_prov"].values()),
        "era5_raw_bytes": sum(sum(Path(audit.REPO_ROOT / f).stat().st_size for f in v["files"]) for v in res["coarse_prov"].values()),
        "glo30_tiles_bytes": sum(v["size_bytes"] for v in tile_info.values()),
        "dataset_parquet_bytes": sum(a["size_bytes"] for a in res["areas"]),
    }
    acq = {
        "type": "Stage4CAcquisitionRecord",
        "design_manifest": _rel(acquire4c.DESIGN_MANIFEST),
        "design_manifest_sha256": _sha(acquire4c.DESIGN_MANIFEST),
        "land_sea_validation": {
            "rule": IS_LAND_RULE, "request": probe_side, "file": _rel(probe), "sha256": _sha(probe),
            "cells_checked": len(res["is_land"]), "land_cells": sum(res["is_land"].values()),
            "non_land_cells": sorted(c for c, v in res["is_land"].items() if not v),
            "cell_status": res["is_land"],
        },
        "elevation_tiles": tile_info,
        "weather_request_batching": {
            "strategy": "one combined area per product per month (union of the frozen per-area request boxes)",
            "era5_land_area_nwse": areas["era5_land"], "era5_area_nwse": areas["era5"],
            "requests": 72, "rationale": "CDS queue cost is per request (fields = variables x hours); 72 requests instead of 792",
        },
        "weather_requests": {
            "era5_land": {k: {"product": "reanalysis-era5-land", **v} for k, v in res["land_prov"].items()},
            "era5": {k: {"product": "reanalysis-era5-single-levels", **v} for k, v in res["coarse_prov"].items()},
        },
        "grids": {"era5_land": res["land_grid"], "era5": res["coarse_grid"]},
        "validity": "all 36 months x 2 products present; hours per month and grid identity verified on load",
        "storage_bytes": storage,
    }
    ACQ_RECORD.write_text(json.dumps(acq, indent=2, ensure_ascii=False), encoding="utf-8")

    rq_target = sum(res["clamped_target_hours_by_cell"][g["era5_land_cell"]] for g in res["gps"])
    manifest = {
        "type": "Stage4ExpandedMultiGpDataset",
        "target_framing": "Target is the ERA5-Land reanalysis proxy — not observation. Coarse input is ERA5 reanalysis. No model trained.",
        "source_note": SOURCE_NOTE,
        "frozen_inputs": {"design_manifest": _rel(acquire4c.DESIGN_MANIFEST),
                          "design_manifest_sha256": _sha(acquire4c.DESIGN_MANIFEST),
                          "protected_artifact_sha256": {k: _sha(p) for k, p in PROTECTED_ARTIFACTS.items()}},
        "dataset_files": res["areas"],
        "columns": COLUMNS,
        "row_grain": "one row per included GP x UTC hour x variable",
        "row_total": res["row_total"],
        "coverage": {
            "areas": len(res["areas"]),
            "gps_included": len(res["gps"]),
            "gps_excluded": len(res["excluded_gps"]),
            "excluded_by_status": dict(Counter(x["status"] for x in res["excluded_gps"])),
            "cells": len(res["target_cells"]),
            "per_area": [{"tp_name": a["tp_name"], "regime": a["geographic_regime"], "gps": a["gps_included"],
                          "cells": len(a["cells"]), "rows": a["rows"]} for a in res["areas"]],
        },
        "corrections": res["corrections"],
        "excluded_gps": res["excluded_gps"],
        "gps": res["gps"],
        "temporal_coverage": {"time_range_utc": res["time_range_utc"], "hours": res["hours"], "months": len(res["months"]),
                              "variables": res["variables"], "units": res["units"],
                              "temporal_split": design["fold_design"]["temporal_split"]},
        "elevation_coverage": {
            "tiles": sorted(tile_info),
            "gps_with_elevation": sum(1 for g in res["gps"] if g["elevation_mean_m"] is not None),
            "gp_mean_elevation_range_m": [min(g["elevation_mean_m"] for g in res["gps"]),
                                          max(g["elevation_mean_m"] for g in res["gps"])],
        },
        "rainfall_quality": {
            "missing_first_hour_per_cell": sorted(set(res["missing_target_by_cell"].values())),
            "missing_target_rows": sum(res["missing_target_by_cell"][g["era5_land_cell"]] for g in res["gps"]),
            "clamped_target_rows": rq_target,
            "max_abs_clamped_step_mm": res["max_abs_clamped_step_mm"],
            "month_boundary_rainfall_missing": res["month_boundary_rainfall_missing"],
            "deaccumulation": "ERA5-Land de-accumulated over the continuous 2021-2023 series (all 36 months concatenated first)",
        },
        "integrity_checks": {
            "complete_gps_match_frozen_design": True,
            "no_cell_shared_between_areas": True,
            "all_target_cells_land": all(res["is_land"][c] for c in res["target_cells"]),
            "bilinear_corners_inside_era5_grid": True,
            "unexpected_missing_values": 0,
            "month_boundary_rainfall_missing": res["month_boundary_rainfall_missing"],
            "months_present": len(res["months"]),
        },
        "pairing": res["pairing"],
        "storage_bytes": storage,
    }
    DATASET_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


if __name__ == "__main__":
    r = build()
    print(f"rows={r['row_total']} gps={len(r['gps'])} cells={len(r['target_cells'])} excluded={len(r['excluded_gps'])}")
