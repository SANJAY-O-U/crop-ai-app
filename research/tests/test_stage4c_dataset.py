"""
Stage 4C acquisition + expanded dataset (research/stage4_spatial_generalization/
acquire4c.py, build4c.py). Contract tests read the committed
stage4c_acquisition_record.json / stage4_dataset_manifest.json; tests that
need the gitignored raw files or Parquet outputs skip where they are absent.
"""

import json
import re

import pandas as pd
import pyarrow.parquet as pq
import pytest

from multi_gp import acquire as p2d
from stage4_spatial_generalization import acquire4c, audit, build4c, grid

HOURS = 26280
N_VARS = 5


@pytest.fixture(scope="module")
def design():
    return acquire4c.load_design()


@pytest.fixture(scope="module")
def record():
    if not build4c.ACQ_RECORD.exists():
        pytest.skip("stage4c_acquisition_record.json not generated")
    return json.loads(build4c.ACQ_RECORD.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest():
    if not build4c.DATASET_MANIFEST.exists():
        pytest.skip("stage4_dataset_manifest.json not generated")
    return json.loads(build4c.DATASET_MANIFEST.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------
# Acquisition plan (no network)
# ---------------------------------------------------------------------

def test_combined_areas_are_union_of_frozen_boxes(design):
    areas = acquire4c.combined_areas(design)
    for e in design["selected"]:
        n, w, s, east = e["era5_land_request_area_nwse"]
        N, W, S, E = areas["era5_land"]
        assert N >= n and W <= w and S <= s and E >= east
        n, w, s, east = e["era5_request_area_nwse"]
        N, W, S, E = areas["era5"]
        assert N >= n and W <= w and S <= s and E >= east
    assert acquire4c.union_area([[2, 0, 1, 1], [3, -1, 0, 0.5]]) == [3, -1, 0, 1]


def test_weather_jobs_72_same_variables_and_hours_as_phase2d(design):
    jobs = acquire4c.weather_jobs(design)
    assert len(jobs) == 72 and len({p for _, _, p in jobs}) == 72
    for dataset, req, path in jobs:
        y, m = int(req["year"][0]), int(req["month"][0])
        ref = p2d.build_era5_land_request(y, m) if dataset == p2d.ERA5_LAND_DATASET else p2d.build_era5_request(y, m)
        assert {k: v for k, v in req.items() if k != "area"} == {k: v for k, v in ref.items() if k != "area"}
        assert "stage4" in path.parts
        assert path not in {p2d.era5_land_path(y, m), p2d.era5_path(y, m)}
    assert {d for d, _, _ in jobs} == {"reanalysis-era5-land", "reanalysis-era5-single-levels"}


def test_uuid_request_id_pattern():
    url = "https://cds.climate.copernicus.eu/api/retrieve/v1/jobs/01e596a4-5d8b-478e-b1c1-6f868d1866d4/results"
    assert acquire4c._UUID.search(url).group(0) == "01e596a4-5d8b-478e-b1c1-6f868d1866d4"


# ---------------------------------------------------------------------
# Land/sea validation + documented correction
# ---------------------------------------------------------------------

def test_land_sea_probe_request_matches_frozen_design(record, design):
    ls = record["land_sea_validation"]
    assert ls["request"]["request"] == design["land_sea_4a"]["required_acquisition"]["request"]
    assert ls["request"]["dataset"] == "reanalysis-era5-land"
    assert re.fullmatch(r"[0-9a-f-]{36}", ls["request"]["request_id"])
    expected = {c for e in design["selected"] for c in e["expected_era5_land_cells"]}
    assert set(ls["cell_status"]) == expected
    if acquire4c.LAND_SEA_PROBE.exists():
        assert audit.sha256(acquire4c.LAND_SEA_PROBE) == ls["sha256"]
        recomputed = build4c.land_status(sorted(expected))
        assert recomputed == ls["cell_status"]


def test_non_land_cells_excluded_not_reassigned(record, manifest):
    non_land = set(record["land_sea_validation"]["non_land_cells"])
    corrected = {c["gp_code"]: c["era5_land_cell"] for c in manifest["corrections"]}
    assert set(corrected.values()) == non_land
    assert not {g["gp_code"] for g in manifest["gps"]} & set(corrected)
    assert all(x["status"] == "NON_LAND_TARGET_CELL" for x in manifest["excluded_gps"] if x["gp_code"] in corrected)
    assert not {g["era5_land_cell"] for g in manifest["gps"]} & non_land


# ---------------------------------------------------------------------
# Identity + coverage
# ---------------------------------------------------------------------

def test_identity_matches_frozen_design(manifest, design):
    by_tp = {e["tp_code"]: e for e in design["selected"]}
    included = {(g["tp_code"], g["gp_code"]): g["era5_land_cell"] for g in manifest["gps"]}
    corrected = {(c["tp_code"], c["gp_code"]) for c in manifest["corrections"]}
    for code, e in by_tp.items():
        frozen = {(code, g["gp_code"]): g["era5_land_cell"] for g in e["spatial_proxy"]["complete_gps"]}
        mine = {k: v for k, v in included.items() if k[0] == code}
        assert set(mine) | {k for k in corrected if k[0] == code} == set(frozen)
        assert all(frozen[k] == v for k, v in mine.items())
    assert {a["tp_code"] for a in manifest["dataset_files"]} == set(by_tp)


def test_no_non_complete_gp_enters_dataset(manifest):
    excluded = {x["gp_code"]: x["status"] for x in manifest["excluded_gps"]}
    assert not set(excluded) & {g["gp_code"] for g in manifest["gps"]}
    assert all(s != "COMPLETE" for s in excluded.values())


def test_coverage_counts(manifest):
    cov = manifest["coverage"]
    assert cov["areas"] == 11 and cov["gps_included"] == len(manifest["gps"])
    assert manifest["row_total"] == cov["gps_included"] * HOURS * N_VARS
    for a in manifest["dataset_files"]:
        assert a["rows"] == a["gps_included"] * HOURS * N_VARS
        assert sum(a["gps_per_cell"].values()) == a["gps_included"]
    assert cov["cells"] == len({g["era5_land_cell"] for g in manifest["gps"]})


def test_no_cell_shared_between_areas(manifest):
    seen = {}
    for a in manifest["dataset_files"]:
        for c in a["cells"]:
            assert c not in seen, f"{c} in {seen.get(c)} and {a['tp_name']}"
            seen[c] = a["tp_name"]


def test_bilinear_corners_inside_era5_request(manifest, record):
    n, w, s, e = record["weather_request_batching"]["era5_area_nwse"]
    for cid, p in manifest["pairing"].items():
        assert abs(sum(c["weight"] for c in p["bilinear"]) - 1) < 1e-9
        for c in p["bilinear"]:
            assert s <= c["latitude"] <= n and w <= c["longitude"] <= e


# ---------------------------------------------------------------------
# Temporal completeness + rainfall
# ---------------------------------------------------------------------

def test_temporal_completeness(manifest, record):
    t = manifest["temporal_coverage"]
    assert t["hours"] == HOURS and t["months"] == 36
    assert t["time_range_utc"] == ["2021-01-01 00:00:00+00:00", "2023-12-31 23:00:00+00:00"]
    for prod in ("era5_land", "era5"):
        months = record["weather_requests"][prod]
        assert len(months) == 36
        assert sum(m["hours"] for m in months.values()) == HOURS


def test_rainfall_quality(manifest):
    rq = manifest["rainfall_quality"]
    assert rq["missing_first_hour_per_cell"] == [1]
    assert rq["missing_target_rows"] == len(manifest["gps"])
    assert rq["month_boundary_rainfall_missing"] == 0
    assert rq["max_abs_clamped_step_mm"] < 1e-3


# ---------------------------------------------------------------------
# Source integrity
# ---------------------------------------------------------------------

def test_raw_sources_match_recorded_hashes(record):
    checked = 0
    for prod in ("era5_land", "era5"):
        for month in record["weather_requests"][prod].values():
            assert re.fullmatch(r"[0-9a-f-]{36}", month["request_id"] or "")
            for f, h in zip(month["files"], month["sha256"]):
                p = audit.REPO_ROOT / f
                if p.exists():
                    assert audit.sha256(p) == h, f
                    checked += 1
    for t in record["elevation_tiles"].values():
        p = audit.REPO_ROOT / t["file"]
        if p.exists():
            assert audit.sha256(p) == t["sha256"]
    if checked == 0:
        pytest.skip("raw Stage 4 files not present locally")


def test_frozen_design_and_protected_artifacts_unchanged(manifest):
    from stage4_spatial_generalization.design import PROTECTED_ARTIFACTS

    frozen = manifest["frozen_inputs"]
    assert audit.sha256(acquire4c.DESIGN_MANIFEST) == frozen["design_manifest_sha256"]
    for k, p in PROTECTED_ARTIFACTS.items():
        assert audit.sha256(p) == frozen["protected_artifact_sha256"][k], k


def test_dataset_files_match_recorded_hashes(manifest):
    present = [a for a in manifest["dataset_files"] if (audit.REPO_ROOT / a["file"]).exists()]
    if not present:
        pytest.skip("Stage 4 Parquet files not present locally")
    for a in present:
        assert audit.sha256(audit.REPO_ROOT / a["file"]) == a["sha256"], a["tp_name"]


# ---------------------------------------------------------------------
# Row-level checks on the Parquet files
# ---------------------------------------------------------------------

def test_parquet_rows_unique_complete_and_labelled(manifest, design):
    diag = {c: f["fold_id"] for f in design["fold_design"]["cell_group_diagnostic"]["folds"] for c in f["test_cells"]}
    present = [a for a in manifest["dataset_files"] if (audit.REPO_ROOT / a["file"]).exists()]
    if not present:
        pytest.skip("Stage 4 Parquet files not present locally")
    for a in present:
        path = audit.REPO_ROOT / a["file"]
        assert pq.read_schema(path).names == build4c.COLUMNS
        df = pq.read_table(path, columns=["panchayat_lgd_code", "timestamp_utc", "variable", "target_value",
                                          "coarse_bilinear_value", "coarse_nearest_value", "cell_group_id",
                                          "taluka_holdout_fold", "regional_holdout_fold", "cell_diagnostic_fold",
                                          "source_note"]).to_pandas()
        assert len(df) == a["rows"]
        assert not df.duplicated(["panchayat_lgd_code", "timestamp_utc", "variable"]).any()
        assert df.groupby("panchayat_lgd_code").size().eq(HOURS * N_VARS).all()
        assert df["timestamp_utc"].nunique() == HOURS
        assert df["source_note"].eq("reanalysis proxy — not observation").all()
        assert df["coarse_bilinear_value"].notna().all() and df["coarse_nearest_value"].notna().all()
        miss = df[df["target_value"].isna()]
        assert miss["variable"].eq("rainfall_mm").all()
        assert miss["timestamp_utc"].eq(pd.Timestamp("2021-01-01T00:00Z")).all()
        assert len(miss) == a["gps_included"]
        assert set(df["cell_group_id"]) == set(a["cells"])
        assert set(df["taluka_holdout_fold"]) == {a["fold_assignment"]["taluka_holdout"]}
        assert set(df["regional_holdout_fold"]) == {a["fold_assignment"]["regional_holdout"]}
        for cid, fold in df.drop_duplicates("cell_group_id").set_index("cell_group_id")["cell_diagnostic_fold"].items():
            assert diag[cid] == fold


def test_train_test_geography_disjoint_in_data(manifest):
    present = [a for a in manifest["dataset_files"] if (audit.REPO_ROOT / a["file"]).exists()]
    if len(present) < len(manifest["dataset_files"]):
        pytest.skip("not all Stage 4 Parquet files present")
    cells = {a["fold_assignment"]["taluka_holdout"]: {grid.parse_cell_id(c) for c in a["cells"]} for a in present}
    gps = {a["fold_assignment"]["taluka_holdout"]: set(pq.read_table(audit.REPO_ROOT / a["file"],
           columns=["panchayat_lgd_code"]).column(0).unique().to_pylist()) for a in present}
    for fold in cells:
        train_cells = set().union(*(v for k, v in cells.items() if k != fold))
        train_gps = set().union(*(v for k, v in gps.items() if k != fold))
        assert not cells[fold] & train_cells and not gps[fold] & train_gps
        assert min(grid.chebyshev_cells(x, y) for x in cells[fold] for y in train_cells) >= 3


# ---------------------------------------------------------------------
# Deterministic rebuild (smallest area)
# ---------------------------------------------------------------------

def test_deterministic_rebuild_of_one_area(manifest, tmp_path):
    smallest = min(manifest["dataset_files"], key=lambda a: a["rows"])
    raw_ok = all((audit.REPO_ROOT / f).exists() for m in json.loads(build4c.ACQ_RECORD.read_text(encoding="utf-8"))
                 ["weather_requests"]["era5_land"].values() for f in m["files"])
    if not raw_ok:
        pytest.skip("raw Stage 4 weather files not present locally")
    res = build4c.build([smallest["tp_code"]], out_dir=tmp_path, write_manifests=False)
    assert audit.sha256(tmp_path / f"{smallest['tp_code']}.parquet") == smallest["sha256"]
    assert res["row_total"] == smallest["rows"]
