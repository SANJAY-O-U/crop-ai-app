"""
Builds the Phase 2D Yelandur multi-GP TRAINING/EVALUATION DATASET:

    data/training/yelandur_multi_gp.parquet         (gitignored data)
    research/multi_gp/yelandur_multi_gp_manifest.json (committed manifest)

This is a REANALYSIS-TO-REANALYSIS SPATIAL-TRANSFER dataset:
    coarse input  = ERA5 0.25 deg (reanalysis-era5-single-levels)
    target proxy  = ERA5-Land 0.1 deg nearest cell to each GP centroid
Neither side is an observation and neither is a forecast. No model is
trained here.

Reads, never modifies: the spatial proxy, elevation, and ERA5-Land linkage
artifacts, and the monthly raw files written by multi_gp/acquire.py.
Reuses the existing pipeline for every unit conversion and the ERA5-Land
precipitation de-accumulation (pipeline.normalize / pipeline.units /
pipeline.coordinates).
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from elevation.elevation_data import LAYER_PATH as ELEVATION_PATH  # noqa: E402
from elevation.elevation_data import load_layer as load_elevation  # noqa: E402
from era5_linkage.era5_linkage_data import LAYER_PATH as LINKAGE_PATH  # noqa: E402
from era5_linkage.era5_linkage_data import load_layer as load_linkage  # noqa: E402
from multi_gp import acquire, pairing, splits  # noqa: E402
from pipeline import units  # noqa: E402
from pipeline.coordinates import extract_point_timeseries  # noqa: E402
from pipeline.normalize import ERA5_LAND_SHORT_NAME_TO_CANONICAL, RAW_VARIABLES, normalize_point_records  # noqa: E402
from spatial_proxy.spatial_proxy_data import load_layer as load_spatial_proxy  # noqa: E402

REPO_ROOT = _RESEARCH_DIR.parent
DATASET_PATH = REPO_ROOT / "data" / "training" / "yelandur_multi_gp.parquet"
MANIFEST_PATH = Path(__file__).resolve().parent / "yelandur_multi_gp_manifest.json"
SPATIAL_PROXY_PATH = _RESEARCH_DIR / "spatial_proxy" / "yelandur_spatial_proxy.json"

SOURCE_NOTE = "reanalysis proxy — not observation"
TARGET_DEFINITION = "era5_land_0.1deg_nearest_cell_to_gp_centroid"
AREA_WEIGHTED_DEFINITION = "era5_land_0.1deg_area_weighted_over_intersecting_cells (secondary diagnostic only)"
COARSE_BILINEAR_DEFINITION = "era5_0.25deg_bilinear_to_target_cell_center"
COARSE_NEAREST_DEFINITION = "era5_0.25deg_nearest_point_to_target_cell_center"
IST_OFFSET = pd.Timedelta(hours=5, minutes=30)
VARIABLES_OUT = ["temperature_c", "dewpoint_c", "relative_humidity_pct", "rainfall_mm", "wind_speed_kmph"]
EXPECTED_COVERAGE = (10, 1, 1)
EXPECTED_PRIMARY_CELL_GROUPS = 4

DATASET_COLUMNS = [
    "panchayat_lgd_code", "gp_name", "taluka_panchayat_lgd_code", "coverage_status", "in_primary_population",
    "timestamp_utc", "local_date_ist", "variable",
    "target_value", "target_unit", "target_definition", "target_missing_reason", "target_rainfall_clamped",
    "cell_group_id", "target_cell_latitude", "target_cell_longitude", "cell_group_complete_gp_count",
    "area_weighted_value", "area_weighted_cell_count", "area_weighted_rainfall_clamped",
    "coarse_bilinear_value", "coarse_nearest_value", "coarse_unit",
    "coarse_nearest_latitude", "coarse_nearest_longitude", "coarse_nearest_distance_km",
    "centroid_latitude", "centroid_longitude", "centroid_to_cell_km", "intersecting_cell_count",
    "elevation_mean_m", "elevation_min_m", "elevation_max_m", "elevation_range_m", "elevation_std_m",
    "temporal_period", "split_fold_1", "split_fold_2", "split_fold_3", "split_fold_4",
    "target_source_file", "target_source_sha256", "coarse_source_file", "coarse_source_sha256",
    "source_note",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _rel(path: Path) -> str:
    return Path(path).resolve().relative_to(REPO_ROOT).as_posix()


def cell_group_id(lat: float, lon: float) -> str:
    return f"E5L_{lat:.2f}N_{lon:.2f}E"


# ---------------------------------------------------------------------
# Raw monthly files -> one continuous Dataset per product
# ---------------------------------------------------------------------

def _load_product(path_fn, expected_lats=None, expected_lons=None):
    """Concatenates every month in the window, checking hour counts and
    that the grid is identical in every month. Returns (dataset, provenance)
    where provenance maps "YYYY-MM" -> {file, sha256, members}."""
    import xarray as xr

    parts, provenance = [], {}
    for year, month in acquire.window_months():
        path = path_fn(year, month)
        if not path.exists():
            raise FileNotFoundError(f"missing monthly file {path} -- run multi_gp/acquire.py first")
        ds = acquire.open_monthly(path)
        n_expected = len(acquire.month_days(year, month)) * 24
        if ds.sizes["valid_time"] != n_expected:
            raise ValueError(f"{path.name}: {ds.sizes['valid_time']} hours, expected {n_expected}")
        lats, lons = ds["latitude"].values, ds["longitude"].values
        if expected_lats is None:
            expected_lats, expected_lons = lats, lons
        if not (np.array_equal(lats, expected_lats) and np.array_equal(lons, expected_lons)):
            raise ValueError(f"{path.name}: grid differs from the rest of the window")
        members = acquire.member_paths(path)
        member_hashes = [sha256_file(p) for p in members]
        provenance[f"{year}-{month:02d}"] = {
            "files": [_rel(p) for p in members],
            "sha256": member_hashes,
            "combined_sha256": hashlib.sha256("".join(member_hashes).encode()).hexdigest(),
        }
        parts.append(ds.drop_vars([v for v in ("expver", "number") if v in ds.variables]))
    combined = xr.concat(parts, dim="valid_time")
    if not combined.indexes["valid_time"].is_monotonic_increasing or combined.indexes["valid_time"].has_duplicates:
        raise ValueError("concatenated time axis is not strictly increasing")
    rename = {k: v for k, v in ERA5_LAND_SHORT_NAME_TO_CANONICAL.items() if k in combined.data_vars}
    rename["valid_time"] = "time"
    return combined.rename(rename), provenance


def _point_series(dataset, lat: float, lon: float, deaccumulate: bool) -> tuple[pd.DataFrame, set]:
    """Long-format normalized series (timestamp, variable, value, unit) for
    one EXACT grid point. For ERA5-Land, precipitation is de-accumulated over
    the whole continuous window with the existing documented rule; returns
    the set of timestamps whose de-accumulation was clamped."""
    lat_idx = np.flatnonzero(dataset["latitude"].values == lat)
    lon_idx = np.flatnonzero(dataset["longitude"].values == lon)
    if len(lat_idx) != 1 or len(lon_idx) != 1:
        raise ValueError(f"({lat}, {lon}) is not an exact grid coordinate of this dataset")
    records = extract_point_timeseries(dataset, lat, lon, RAW_VARIABLES)
    if records[0]["grid_distance_km"] != 0.0:
        raise ValueError(f"({lat}, {lon}) did not select itself exactly")

    clamped, max_clamped_mm = set(), 0.0
    if deaccumulate:
        raw = [r["total_precipitation"] for r in records]
        hours = [pd.Timestamp(r["time"]).hour for r in records]
        hourly, anomalies = units.deaccumulate_era5_land_precipitation_m(raw, hours)
        for rec, value in zip(records, hourly):
            rec["total_precipitation"] = value
        clamped = {pd.Timestamp(records[i]["time"]).tz_localize("UTC") for i in anomalies}
        if anomalies:
            max_clamped_mm = max(units.precipitation_m_to_mm(raw[i - 1] - raw[i]) for i in anomalies)

    df = normalize_point_records(records, lat, lon)
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize("UTC")
    return df[["timestamp", "variable", "value", "unit"]], clamped, max_clamped_mm


def _wide(series: pd.DataFrame, full_index: pd.MultiIndex) -> pd.Series:
    return series.set_index(["timestamp", "variable"])["value"].reindex(full_index)


# ---------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------

def load_inputs() -> dict:
    spatial_proxy = load_spatial_proxy()
    elevation = load_elevation()
    linkage_layer = load_linkage()
    if linkage_layer["acquisition_status"] != "AVAILABLE":
        raise RuntimeError("ERA5-Land linkage is not AVAILABLE -- cannot build Phase 2D")

    status = [gp["geometry_status"] for gp in spatial_proxy["panchayats"]]
    actual = (status.count("COMPLETE"), status.count("PARTIAL"), status.count("UNAVAILABLE"))
    if actual != EXPECTED_COVERAGE:
        raise RuntimeError(f"STOP: coverage {actual} != expected {EXPECTED_COVERAGE}")
    return {"spatial_proxy": spatial_proxy, "elevation": elevation, "linkage": linkage_layer}


def gp_static_records(inputs: dict, era5_land_lats, era5_land_lons) -> list[dict]:
    proxy_by_code = {gp["panchayat_lgd_code"]: gp for gp in inputs["spatial_proxy"]["panchayats"]}
    elev_by_code = {gp["gp_id"]: gp for gp in inputs["elevation"]["panchayats"]}
    records = []
    for link in inputs["linkage"]["panchayats"]:
        code = link["panchayat_lgd_code"]
        proxy = proxy_by_code[code]
        elev = elev_by_code.get(code, {})
        rec = {
            "panchayat_lgd_code": code,
            "gp_name": link["gp_name"],
            "taluka_panchayat_lgd_code": proxy["taluka_panchayat_lgd_code"],
            "coverage_status": link["coverage_status"],
            "in_primary_population": link["coverage_status"] == "COMPLETE",
        }
        if link["coverage_status"] == "UNAVAILABLE":
            rec["available"] = False
            records.append(rec)
            continue
        cell_lat, cell_lon = link["nearest_grid_latitude"], link["nearest_grid_longitude"]
        weights = pairing.area_weights(proxy["geometry"], era5_land_lats, era5_land_lons, link["intersecting_cells"])
        rec.update({
            "available": True,
            "cell_group_id": cell_group_id(cell_lat, cell_lon),
            "target_cell_latitude": cell_lat,
            "target_cell_longitude": cell_lon,
            "centroid_latitude": link["centroid_latitude"],
            "centroid_longitude": link["centroid_longitude"],
            "centroid_to_cell_km": link["centroid_to_grid_distance_km"],
            "intersecting_cell_count": link["intersecting_cell_count"],
            "area_weights": weights,
            "elevation_mean_m": elev.get("mean_m"),
            "elevation_min_m": elev.get("min_m"),
            "elevation_max_m": elev.get("max_m"),
            "elevation_range_m": elev.get("range_m"),
            "elevation_std_m": elev.get("std_m"),
        })
        records.append(rec)

    complete_counts = {}
    for rec in records:
        if rec["available"] and rec["in_primary_population"]:
            complete_counts[rec["cell_group_id"]] = complete_counts.get(rec["cell_group_id"], 0) + 1
    for rec in records:
        if rec["available"]:
            rec["cell_group_complete_gp_count"] = complete_counts.get(rec["cell_group_id"], 0)
    if len(complete_counts) != EXPECTED_PRIMARY_CELL_GROUPS:
        raise RuntimeError(f"STOP: {len(complete_counts)} primary cell groups, expected {EXPECTED_PRIMARY_CELL_GROUPS}")
    return records


def build() -> tuple[pd.DataFrame, dict]:
    inputs = load_inputs()
    grid_meta = inputs["linkage"]["grid_metadata"]

    land, land_prov = _load_product(acquire.era5_land_path)
    coarse, coarse_prov = _load_product(acquire.era5_path)
    land_lats, land_lons = land["latitude"].values, land["longitude"].values
    if (len(land_lats), len(land_lons)) != (grid_meta["n_latitude"], grid_meta["n_longitude"]) or not (
        land_lats.min() == grid_meta["latitude_min"] and land_lats.max() == grid_meta["latitude_max"]
        and land_lons.min() == grid_meta["longitude_min"] and land_lons.max() == grid_meta["longitude_max"]
    ):
        raise ValueError("multi-year ERA5-Land grid differs from the Phase 2C linkage grid")

    gps = gp_static_records(inputs, land_lats, land_lons)
    available = [g for g in gps if g["available"]]

    hours = pd.DatetimeIndex(pd.to_datetime(land["time"].values)).tz_localize("UTC")
    coarse_hours = pd.DatetimeIndex(pd.to_datetime(coarse["time"].values)).tz_localize("UTC")
    if not hours.equals(coarse_hours):
        raise ValueError("ERA5 and ERA5-Land time axes differ")
    full_index = pd.MultiIndex.from_product([hours, VARIABLES_OUT], names=["timestamp", "variable"])

    # ERA5-Land cells: every target cell + every intersecting cell (for the diagnostic)
    needed_cells = sorted({(g["target_cell_latitude"], g["target_cell_longitude"]) for g in available}
                          | {c for g in available for c in g["area_weights"]})
    land_values, land_clamped, units_by_var = {}, {}, {}
    max_clamped_mm = 0.0
    for lat, lon in needed_cells:
        df, clamped, cell_max = _point_series(land, lat, lon, deaccumulate=True)
        land_values[(lat, lon)] = _wide(df, full_index)
        land_clamped[(lat, lon)] = clamped
        max_clamped_mm = max(max_clamped_mm, cell_max)
        units_by_var.update(dict(zip(df["variable"], df["unit"])))

    # ERA5 coarse pairing per target cell
    c_lats, c_lons = coarse["latitude"].values, coarse["longitude"].values
    target_cells = sorted({(g["target_cell_latitude"], g["target_cell_longitude"]) for g in available})
    coarse_pairing, coarse_points = {}, set()
    for lat, lon in target_cells:
        corners = pairing.bilinear_weights(c_lats, c_lons, lat, lon)
        nearest = pairing.nearest_coarse_point(c_lats, c_lons, lat, lon)
        coarse_pairing[(lat, lon)] = {"bilinear": corners, "nearest": nearest}
        coarse_points |= {(a, b) for a, b, _ in corners} | {nearest[:2]}
    coarse_values, coarse_units = {}, {}
    for lat, lon in sorted(coarse_points):
        df, _, _ = _point_series(coarse, lat, lon, deaccumulate=False)  # ERA5 tp is already hourly
        coarse_values[(lat, lon)] = _wide(df, full_index)
        coarse_units.update(dict(zip(df["variable"], df["unit"])))
    if coarse_units != units_by_var:
        raise ValueError(f"coarse/target unit mismatch: {coarse_units} vs {units_by_var}")
    negative_coarse_rain = int(sum((coarse_values[p].xs("rainfall_mm", level="variable") < 0).sum() for p in coarse_points))

    ts_col = full_index.get_level_values("timestamp")
    var_col = full_index.get_level_values("variable")
    month_key = ts_col.strftime("%Y-%m")

    frames = []
    for g in available:
        cell = (g["target_cell_latitude"], g["target_cell_longitude"])
        target = land_values[cell].to_numpy()
        is_rain = var_col == "rainfall_mm"

        area = np.zeros(len(full_index))
        for c, w in g["area_weights"].items():
            area = area + w * land_values[c].to_numpy()  # NaN propagates -- never filled

        cp = coarse_pairing[cell]
        bilinear = np.zeros(len(full_index))
        for a, b, w in cp["bilinear"]:
            bilinear = bilinear + w * coarse_values[(a, b)].to_numpy()
        nlat, nlon, ndist = cp["nearest"]

        frame = pd.DataFrame({
            "timestamp_utc": ts_col,
            "variable": var_col,
            "target_value": target,
            "target_unit": [units_by_var[v] for v in var_col],
            "area_weighted_value": area,
            "coarse_bilinear_value": bilinear,
            "coarse_nearest_value": coarse_values[(nlat, nlon)].to_numpy(),
            "coarse_unit": [coarse_units[v] for v in var_col],
            "target_rainfall_clamped": is_rain & ts_col.isin(list(land_clamped[cell])),
            "area_weighted_rainfall_clamped": is_rain & ts_col.isin(
                list(set().union(*(land_clamped[c] for c in g["area_weights"])))),
            "target_source_file": [land_prov[k]["files"][0] for k in month_key],
            "target_source_sha256": [land_prov[k]["combined_sha256"] for k in month_key],
            "coarse_source_file": ["|".join(coarse_prov[k]["files"]) for k in month_key],
            "coarse_source_sha256": [coarse_prov[k]["combined_sha256"] for k in month_key],
        })
        frame["target_missing_reason"] = np.where(
            np.isnan(target),
            np.where(is_rain, "ERA5_LAND_DEACCUMULATION_FIRST_STEP", "MISSING_IN_SOURCE"),
            None,
        )
        for key in ("panchayat_lgd_code", "gp_name", "taluka_panchayat_lgd_code", "coverage_status",
                    "in_primary_population", "cell_group_id", "target_cell_latitude", "target_cell_longitude",
                    "cell_group_complete_gp_count", "centroid_latitude", "centroid_longitude",
                    "centroid_to_cell_km", "intersecting_cell_count", "elevation_mean_m", "elevation_min_m",
                    "elevation_max_m", "elevation_range_m", "elevation_std_m"):
            frame[key] = g[key]
        frame["area_weighted_cell_count"] = len(g["area_weights"])
        frame["coarse_nearest_latitude"] = nlat
        frame["coarse_nearest_longitude"] = nlon
        frame["coarse_nearest_distance_km"] = ndist
        frames.append(frame)

    data = pd.concat(frames, ignore_index=True)
    data["local_date_ist"] = (data["timestamp_utc"] + IST_OFFSET).dt.strftime("%Y-%m-%d")
    data["target_definition"] = TARGET_DEFINITION
    data["source_note"] = SOURCE_NOTE

    data["temporal_period"] = splits.temporal_period(data["timestamp_utc"])
    primary_groups = splits.spatial_folds(g["cell_group_id"] for g in available if g["in_primary_population"])
    target_missing = data["target_value"].isna()
    for k, group in enumerate(primary_groups, start=1):
        data[f"split_fold_{k}"] = splits.fold_roles(
            data["cell_group_id"], data["in_primary_population"], data["temporal_period"], target_missing, group)

    data = data[DATASET_COLUMNS].sort_values(["panchayat_lgd_code", "timestamp_utc", "variable"], kind="stable")
    data = data.reset_index(drop=True)

    manifest = build_manifest(data, gps, primary_groups, coarse_pairing, land_prov, coarse_prov,
                              units_by_var, negative_coarse_rain, land_lats, land_lons, c_lats, c_lons,
                              max_clamped_mm)
    return data, manifest


def build_manifest(data, gps, primary_groups, coarse_pairing, land_prov, coarse_prov,
                   units_by_var, negative_coarse_rain, land_lats, land_lons, c_lats, c_lons,
                   max_clamped_mm) -> dict:
    fold_summary = []
    for k, group in enumerate(primary_groups, start=1):
        col = data[f"split_fold_{k}"]
        train, test = data[col == "train"], data[col == "test"]
        fold_summary.append({
            "fold": k,
            "column": f"split_fold_{k}",
            "held_out_cell_group": group,
            "test_gps": sorted(test["gp_name"].unique().tolist()),
            "train_cell_groups": sorted(train["cell_group_id"].unique().tolist()),
            "train_rows": int(len(train)),
            "test_rows": int(len(test)),
            "train_time_range_utc": [str(train["timestamp_utc"].min()), str(train["timestamp_utc"].max())],
            "test_time_range_utc": [str(test["timestamp_utc"].min()), str(test["timestamp_utc"].max())],
        })

    def groups_summary():
        out = {}
        for g in gps:
            if g["available"]:
                out.setdefault(g["cell_group_id"], {"cell_latitude": g["target_cell_latitude"],
                                                    "cell_longitude": g["target_cell_longitude"],
                                                    "complete_gps": [], "partial_gps": []})
                key = "complete_gps" if g["in_primary_population"] else "partial_gps"
                out[g["cell_group_id"]][key].append(g["gp_name"])
        return dict(sorted(out.items()))

    return {
        "type": "YelandurMultiGpSpatialTransferDataset",
        "phase": "2D",
        "dataset_file": _rel(DATASET_PATH),
        "dataset_file_note": "Parquet data file is gitignored (data/training/**); regenerate with research/multi_gp/build.py.",
        "row_count": int(len(data)),
        "row_grain": "one row per available GP x UTC hour x variable",
        "columns": DATASET_COLUMNS,
        "experiment_framing": (
            "Reanalysis-to-reanalysis spatial-transfer experiment: ERA5 0.25 deg reanalysis (coarse input) "
            "paired with ERA5-Land 0.1 deg reanalysis (target proxy). Neither side is an observation and "
            "neither is a forecast product. No model has been trained on this dataset."
        ),
        "source_note": SOURCE_NOTE,
        "target": {
            "definition": TARGET_DEFINITION,
            "description": (
                "ERA5-Land 0.1 deg hourly value of the grid cell nearest each GP's spatial-proxy centroid "
                "(nearest cell as recorded in the Phase 2C linkage artifact). GPs that share a nearest cell "
                "share an identical target series."
            ),
            "dataset": acquire.ERA5_LAND_DATASET,
            "product_type": "reanalysis",
            "grid": {"latitudes": [float(x) for x in land_lats], "longitudes": [float(x) for x in land_lons],
                     "latitude_order": "descending", "longitude_order": "ascending", "spacing_deg": 0.1},
            "request_area_nwse": list(acquire.ERA5_LAND_AREA),
        },
        "secondary_diagnostic": {
            "column": "area_weighted_value",
            "definition": AREA_WEIGHTED_DEFINITION,
            "description": (
                "Area-weighted mean of ERA5-Land values over the cells a GP's spatial-proxy geometry "
                "intersects (weights = intersected area in EPSG:32643, normalized to 1). A deterministic "
                "reweighting of the same reanalysis cells -- NOT the primary target, and differences between "
                "GPs it produces are geometric, not evidence of sub-grid variability."
            ),
            "weights_by_gp": {g["gp_name"]: {f"{la},{lo}": round(w, 6) for (la, lo), w in g["area_weights"].items()}
                              for g in gps if g["available"]},
        },
        "coarse_input": {
            "dataset": acquire.ERA5_DATASET,
            "product_type": "reanalysis",
            "is_forecast": False,
            "grid": {"latitudes": [float(x) for x in c_lats], "longitudes": [float(x) for x in c_lons],
                     "latitude_order": "descending", "longitude_order": "ascending", "spacing_deg": 0.25},
            "request_area_nwse": list(acquire.ERA5_AREA),
            "columns": {
                "coarse_bilinear_value": COARSE_BILINEAR_DEFINITION,
                "coarse_nearest_value": COARSE_NEAREST_DEFINITION,
            },
            "pairing_note": (
                "Pairing is per ERA5-Land TARGET CELL, using ERA5 values only. Bilinear weights come from the "
                "4 ERA5 points enclosing the target cell center. The nearest-point field is recorded for "
                "transparency but collapses three of the four primary cell groups onto the same ERA5 point, "
                "so it alone cannot distinguish them. Derived variables (RH, wind speed) are computed at each "
                "ERA5 point first, then interpolated."
            ),
            "pairing_by_target_cell": {
                cell_group_id(lat, lon): {
                    "bilinear": [{"latitude": a, "longitude": b, "weight": round(w, 6)} for a, b, w in p["bilinear"]],
                    "nearest": {"latitude": p["nearest"][0], "longitude": p["nearest"][1],
                                "distance_km": round(p["nearest"][2], 4)},
                } for (lat, lon), p in sorted(coarse_pairing.items())
            },
            "negative_hourly_rainfall_values": negative_coarse_rain,
        },
        "variables": {v: units_by_var[v] for v in VARIABLES_OUT},
        "time": {
            "window_utc": [str(data["timestamp_utc"].min()), str(data["timestamp_utc"].max())],
            "hours": int(data["timestamp_utc"].nunique()),
            "timestamp_convention": "timestamp_utc is the ERA5/ERA5-Land valid_time in UTC.",
            "local_date_ist": "UTC+05:30 calendar date of timestamp_utc, for display only; never used for splitting.",
            "rainfall_convention": (
                "rainfall_mm is the accumulation over the hour ENDING at timestamp_utc for both products. "
                "ERA5-Land is de-accumulated (since-00-UTC accumulation) over the whole continuous window with "
                "pipeline.units.deaccumulate_era5_land_precipitation_m; ERA5 single-levels tp is already hourly."
            ),
            "pilot_window_note": "The Phase 2A 72-hour pilot files are untouched and are not used here.",
        },
        "rainfall_quality": {
            "target_missing_rows": int(data["target_value"].isna().sum()),
            "target_missing_reason_counts": data["target_missing_reason"].value_counts().to_dict(),
            "target_rainfall_clamped_rows": int(data["target_rainfall_clamped"].sum()),
            "area_weighted_rainfall_clamped_rows": int(data["area_weighted_rainfall_clamped"].sum()),
            "max_abs_clamped_step_mm": max_clamped_mm,
            "clamping_note": (
                "Clamped steps are ERA5-Land within-cycle accumulation DECREASES set to 0.0 by the existing "
                "de-accumulation rule. Their largest magnitude is recorded above; values this small are "
                "consistent with float32 storage rounding of an unchanged accumulation, not rainfall."
            ),
        },
        "coverage": {
            "expected_gp_count": 12,
            "complete_gp_count": 10,
            "partial_gp_count": 1,
            "unavailable_gp_count": 1,
            "primary_evaluation_population": sorted(g["gp_name"] for g in gps if g["available"] and g["in_primary_population"]),
            "partial": {"Agara": "Included with rows, flagged coverage_status=PARTIAL, in_primary_population=False, "
                                 "and 'excluded' in every fold; excluded from primary metrics."},
            "unavailable": {"Mamballi": "Zero data rows. No geometry, elevation, or weather is inferred."},
            "rows_by_gp": data.groupby("gp_name").size().to_dict(),
        },
        "spatial_groups": {
            "effective_spatial_sample_size": len(primary_groups),
            "statement": (
                f"The effective spatial sample size is {len(primary_groups)} ERA5-Land cell groups, not 10 GPs: "
                "GPs sharing a nearest ERA5-Land cell have identical target series."
            ),
            "cell_groups": groups_summary(),
        },
        "split_methodology": {
            "spatial": "Leave-one-cell-group-out over the primary (COMPLETE) population: one fold per cell group.",
            "temporal": {
                "train_period_utc": [str(splits.TRAIN_START), str(splits.EMBARGO_START - pd.Timedelta(hours=1))],
                "embargo_utc": [str(splits.EMBARGO_START), str(splits.TEST_START - pd.Timedelta(hours=1))],
                "test_period_utc": [str(splits.TEST_START), str(splits.TEST_END_EXCLUSIVE - pd.Timedelta(hours=1))],
                "note": "Forward-in-time blocked holdout identical for every spatial fold; 7-day embargo unused.",
            },
            "roles": {
                "train": "primary population, not the held-out cell group, train_period",
                "test": "primary population, the held-out cell group, test_period",
                "excluded": "everything else (incl. PARTIAL GPs, embargo, rows with a missing target)",
            },
            "guarantees": [
                "No cell group appears in both train and test of any fold.",
                "No train timestamp is within 7 days of any test timestamp.",
                "No individual hourly row is randomly assigned.",
            ],
            "folds": fold_summary,
        },
        "provenance": {
            "spatial_proxy": {"file": _rel(SPATIAL_PROXY_PATH), "sha256": sha256_file(SPATIAL_PROXY_PATH)},
            "elevation": {"file": _rel(ELEVATION_PATH), "sha256": sha256_file(ELEVATION_PATH),
                          "source": "Copernicus DEM GLO-30 zonal statistics over the spatial-proxy geometry"},
            "era5_linkage": {"file": _rel(LINKAGE_PATH), "sha256": sha256_file(LINKAGE_PATH)},
            "era5_land_monthly_files": land_prov,
            "era5_monthly_files": coarse_prov,
            "acquisition_module": "research/multi_gp/acquire.py (auth via config.get_cds_client)",
        },
        "known_limitations": [
            "Both input and target are reanalysis; metrics measure agreement with ERA5-Land, not with actual "
            "Panchayat weather. The target is a reanalysis proxy, not an observation.",
            "Effective spatial sample size is 4 cell groups; neighbouring ERA5-Land cells are highly correlated.",
            "No sub-grid (finer than ~9-11 km) skill can be evaluated with this target.",
            "GPs in the same cell group have identical targets; their rows are not independent samples.",
            "ERA5-Land model orography was not acquired; GLO-30 elevation describes the GP geometry, not the "
            "terrain ERA5-Land represents.",
            "Geometries are a 1991-vintage historical village-union spatial proxy, not present-day GP boundaries.",
            "Agara is PARTIAL (Kinakahalli missing); Mamballi is UNAVAILABLE.",
            "Single forward temporal holdout (one test year); results may reflect 2023-specific conditions.",
        ],
    }


def main() -> int:
    data, manifest = build()
    DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    data.to_parquet(DATASET_PATH, index=False)
    manifest["dataset_file_sha256"] = sha256_file(DATASET_PATH)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"Wrote {len(data)} rows -> {DATASET_PATH}")
    print(f"Wrote manifest -> {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
