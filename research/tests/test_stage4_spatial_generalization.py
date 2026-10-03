"""
Stage 4 feasibility audit (research/stage4_spatial_generalization/).

  - Audit calculations on small synthetic inputs (always run).
  - Grid convention re-checked against REAL acquired ERA5 / ERA5-Land files
    (skipped where the gitignored raw files are absent).
  - Provenance / consistency contract tests on the committed
    feasibility_audit.json and taluka_panchayat_audit.csv.
"""

import csv
import json

import numpy as np
import pytest
import shapely.geometry as sgeom

from stage4_spatial_generalization import audit, criteria, grid

FORBIDDEN_PHRASES = [
    "ground truth", "observed panchayat weather", "validated panchayat forecast",
    "accurate panchayat weather", "actual panchayat weather prediction",
]


# ---------------------------------------------------------------------
# Grid arithmetic
# ---------------------------------------------------------------------

def test_nearest_cell_basic_and_half_way():
    assert grid.era5_land_cell(12.04, 77.06) == (12.0, 77.1)
    assert grid.era5_cell(12.125, 77.375) == (12.25, 77.5)  # exactly representable half-way -> up, consistently
    assert grid.era5_cell(12.13, 77.12) == (12.25, 77.0)
    assert grid.cell_id((12.0, 77.19999999999999)) == "E5L_12.00N_77.20E"


def test_chebyshev_and_enclosing_box():
    assert grid.chebyshev_cells((12.0, 77.1), (12.1, 77.2)) == 1
    assert grid.chebyshev_cells((12.0, 77.1), (12.3, 77.1)) == 3
    assert grid.enclosing_era5_box((12.1, 77.1)) == (12.0, 77.0)
    assert grid.enclosing_era5_box((12.0, 77.2)) == (12.0, 77.0)
    assert grid.enclosing_era5_box((12.25, 77.3)) == (12.25, 77.25)


def _real_coords(path):
    import xarray as xr

    if not path.exists():
        pytest.skip(f"{path.name} not present locally")
    with xr.open_dataset(path) as ds:
        return ds["latitude"].values, ds["longitude"].values


@pytest.mark.parametrize("name", ["era5_land_yelandur_202306.nc", "era5_land_pilot_202306.nc"])
def test_era5_land_rounding_matches_real_grid_argmin(name):
    lats, lons = _real_coords(audit.RAW / "era5_land" / name)
    rng = np.random.default_rng(0)
    for _ in range(500):
        lat = rng.uniform(lats.min(), lats.max())
        lon = rng.uniform(lons.min(), lons.max())
        exp = (float(lats[np.argmin(np.abs(lats - lat))]), float(lons[np.argmin(np.abs(lons - lon))]))
        got = grid.era5_land_cell(lat, lon)
        assert got[0] == pytest.approx(exp[0], abs=1e-9) and got[1] == pytest.approx(exp[1], abs=1e-9)


def test_era5_rounding_matches_real_grid_argmin():
    lats, lons = _real_coords(audit.RAW / "era5" / "multi_gp" / "era5_yelandur_202101.nc")
    rng = np.random.default_rng(1)
    for _ in range(500):
        lat, lon = rng.uniform(lats.min(), lats.max()), rng.uniform(lons.min(), lons.max())
        got = grid.era5_cell(lat, lon)
        assert got[0] == pytest.approx(float(lats[np.argmin(np.abs(lats - lat))]))
        assert got[1] == pytest.approx(float(lons[np.argmin(np.abs(lons - lon))]))


# ---------------------------------------------------------------------
# Spatial-proxy record: exact code only, never repaired
# ---------------------------------------------------------------------

def _feat(code, geom):
    return {"properties": {"V_CT_CODE": code, "NAME": "X"}, "geometry": sgeom.mapping(geom)}


BOX_A = sgeom.box(77.00, 12.00, 77.02, 12.02)
BOX_B = sgeom.box(77.02, 12.00, 77.04, 12.02)
BOWTIE = sgeom.Polygon([(77.0, 12.0), (77.02, 12.02), (77.02, 12.0), (77.0, 12.02)])
GP = {"gp_code": "1", "gp_name": "G", "tp_code": "10", "tp_name": "T", "zp_code": "100", "zp_name": "Z"}


def _index(*feats):
    from spatial_proxy.matching import index_datameet_features_by_vct_code

    return index_datameet_features_by_vct_code(list(feats))


def _v(code, shared=False, name="V"):
    return {"village_code": "x", "village_name": name, "census_2001_code": code, "shared_with_other_gp": shared}


def test_complete_gp_centroid_and_cell():
    rec = audit.gp_proxy_record(GP, [_v("123"), _v("124")], _index(_feat("00000123", BOX_A), _feat("00000124", BOX_B)))
    assert rec["status"] == "COMPLETE" and rec["n_matched"] == 2
    assert rec["centroid_lat"] == pytest.approx(12.01, abs=1e-4) and rec["centroid_lon"] == pytest.approx(77.02, abs=1e-4)
    assert rec["era5_land_cell"] == [12.0, 77.0]


def test_partial_unavailable_and_no_villages():
    idx = _index(_feat("00000123", BOX_A))
    assert audit.gp_proxy_record(GP, [_v("123"), _v("999")], idx)["status"] == "PARTIAL"
    assert audit.gp_proxy_record(GP, [_v("999")], idx)["status"] == "UNAVAILABLE"
    assert audit.gp_proxy_record(GP, [], idx)["status"] == "NO_LGD_VILLAGES"
    assert audit.gp_proxy_record(GP, [_v("")], idx)["status"] == "UNAVAILABLE"
    assert audit.gp_proxy_record(GP, [_v("0")], idx)["status"] == "UNAVAILABLE"


def test_matching_is_exact_code_only_no_name_fallback():
    feat = {"properties": {"V_CT_CODE": "00000555", "NAME": "SAMENAME", "VILL_NAME": "SAMENAME"},
            "geometry": sgeom.mapping(BOX_A)}
    rec = audit.gp_proxy_record(GP, [_v("777", name="SAMENAME")], _index(feat))
    assert rec["status"] == "UNAVAILABLE" and rec["n_matched"] == 0


def test_invalid_geometry_is_reported_not_repaired():
    rec = audit.gp_proxy_record(GP, [_v("123")], _index(_feat("00000123", BOWTIE)))
    assert rec["status"] == "INVALID_GEOMETRY" and rec["n_invalid_source_geometries"] == 1
    assert "centroid_lat" not in rec


def test_shared_village_flag():
    rec = audit.gp_proxy_record(GP, [_v("123", shared=True)], _index(_feat("00000123", BOX_A)))
    assert rec["status"] == "COMPLETE" and rec["has_shared_village"]


# ---------------------------------------------------------------------
# Candidate summary + decision rules
# ---------------------------------------------------------------------

def _complete(code, lat, lon, shared=False):
    return {**GP, "gp_code": code, "status": "COMPLETE", "n_villages": 1, "n_matched": 1, "has_shared_village": shared,
            "centroid_lat": lat, "centroid_lon": lon, "bounds": [lon - 0.01, lat - 0.01, lon + 0.01, lat + 0.01],
            "era5_land_cell": list(grid.era5_land_cell(lat, lon)),
            "era5_box": list(grid.enclosing_era5_box(grid.era5_land_cell(lat, lon)))}


def _summ(recs, tp="10", in_ka=True, yel=((12.0, 77.1),), yel_centroid=(12.05, 77.1)):
    cells = {tuple(r["era5_land_cell"]) for r in recs if r["status"] == "COMPLETE"}
    tiles = {audit.full_tile_name(k) for k in ("N15_00_E075_00", "N12_00_E077_00")}
    return audit.summarize_candidate(tp, recs, set(yel), yel_centroid, tiles,
                                     {c: in_ka for c in cells}, {c: 1 for c in cells})


def test_summary_counts_cells_and_gps_per_cell():
    recs = [_complete("1", 15.01, 75.01), _complete("2", 15.02, 75.02), _complete("3", 15.31, 75.31),
            _complete("4", 15.51, 75.51), {**GP, "gp_code": "5", "status": "PARTIAL", "n_villages": 2, "n_matched": 1,
                                           "has_shared_village": False}]
    s = _summ(recs)
    assert s["administrative"]["lgd_gps"] == 5
    assert s["spatial_proxy"]["complete_gps"] == 4 and s["spatial_proxy"]["complete_share"] == 0.8
    assert s["grid"]["era5_land_cells"] == 3 and s["grid"]["new_era5_land_cells_vs_yelandur"] == 3
    assert s["grid"]["complete_gps_per_cell"] == {"min": 1, "median": 1, "max": 2}
    assert s["grid"]["cells_with_single_gp"] == 2
    assert s["elevation"]["all_tiles_publicly_listed"] is True
    assert s["decision"] == "RECOMMEND_FOR_SHORTLIST"


def test_cells_used_by_yelandur_are_not_new_and_adjacency_counted():
    recs = [_complete("1", 12.0, 77.1), _complete("2", 12.1, 77.2), _complete("3", 12.5, 77.5)]
    s = _summ(recs)
    assert s["grid"]["new_era5_land_cells_vs_yelandur"] == 2
    assert s["grid"]["new_cells_adjacent_to_yelandur_cells"] == 1


def test_decision_rules_and_boundaries():
    far = [_complete(str(i), 15.0 + 0.2 * i, 75.0) for i in range(3)]
    assert _summ(far)["decision"] == "RECOMMEND_FOR_SHORTLIST"
    two_cells = far[:2]
    assert _summ(two_cells)["decision"] == "EXCLUDE"
    near = [_complete(str(i), 12.3 + 0.1 * i, 77.1) for i in range(3)]
    s = _summ(near)
    assert s["decision"] == "EXCLUDE" and any("distance" in r for r in s["reasons"])
    low_share = far + [{**GP, "gp_code": str(9 + i), "status": "PARTIAL", "n_villages": 2, "n_matched": 1,
                        "has_shared_village": False} for i in range(1)]
    assert _summ(low_share)["spatial_proxy"]["complete_share"] == 0.75
    assert _summ(low_share)["decision"] == "EXCLUDE"


def test_conditional_flags():
    far = [_complete(str(i), 15.0 + 0.2 * i, 75.0) for i in range(3)]
    assert _summ(far, in_ka=False)["decision"] == "CONDITIONAL"
    shared = far[:2] + [_complete("9", 15.4, 75.0, shared=True)]
    assert _summ(shared)["decision"] == "CONDITIONAL"


def test_yelandur_itself_is_frozen():
    recs = [_complete(str(i), 15.0 + 0.2 * i, 75.0) for i in range(3)]
    assert _summ(recs, tp=criteria.YELANDUR_TALUKA_PANCHAYAT_CODE)["decision"] == "FROZEN_EXISTING"


def test_gp_hierarchy_requires_full_lgd_chain(tmp_path):
    header = "Localbody Type Code,Localbody Type Name,Localbody Code,Localbody Name (In English),Parent Localbody Code,State Name\n"
    good = tmp_path / "good.csv"
    good.write_text(header + "1,Zila Panchayat,100,Z,0,Karnataka\n2,Taluka Panchayat,10,T,100,Karnataka\n"
                    "3,Gram Panchayat,1,G,10,Karnataka\n3,Gram Panchayat,2,H,10,Kerala\n", encoding="utf-8")
    gps = audit.load_gp_hierarchy(good)
    assert gps == {"1": {"gp_code": "1", "gp_name": "G", "tp_code": "10", "tp_name": "T", "zp_code": "100", "zp_name": "Z"}}
    bad = tmp_path / "bad.csv"
    bad.write_text(header + "3,Gram Panchayat,1,G,999,Karnataka\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        audit.load_gp_hierarchy(bad)


# ---------------------------------------------------------------------
# Provenance / consistency of the committed audit
# ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def result():
    if not audit.RESULTS_PATH.exists():
        pytest.skip("feasibility_audit.json not generated")
    return json.loads(audit.RESULTS_PATH.read_text(encoding="utf-8"))


def test_source_hashes_match_files_on_disk(result):
    for key, path in audit.SOURCES.items():
        if not path.exists():
            pytest.skip(f"{path.name} not present locally")
        assert audit.sha256(path) == result["provenance"]["source_sha256"][key], key


def test_yelandur_reproduced_against_frozen_artifacts(result):
    r = result["yelandur_reproduction_check"]
    assert r["reproduced"] and r["status_matches"] == r["status_compared"] == 12
    assert r["nearest_cell_matches"] == r["nearest_cell_compared"] == 10
    assert r["max_centroid_difference_deg"] == 0.0 and r["distinct_complete_cells"] == 4
    linkage = json.loads(audit.SOURCES["yelandur_era5_linkage"].read_text(encoding="utf-8"))
    frozen = sorted({grid.cell_id((g["nearest_grid_latitude"], g["nearest_grid_longitude"]))
                     for g in linkage["panchayats"] if g["coverage_status"] == "COMPLETE"})
    assert result["statewide"]["yelandur_cells"] == frozen


def test_criteria_recorded_match_module(result):
    for k, v in result["criteria"].items():
        assert getattr(criteria, k) == v


def test_counts_are_internally_consistent(result):
    sw = result["statewide"]
    assert sum(sw["gp_status_counts"].values()) == sw["lgd_gram_panchayats"]
    assert sum(c["administrative"]["lgd_gps"] for c in result["candidates"]) == sw["lgd_gram_panchayats"]
    assert sum(c["spatial_proxy"]["complete_gps"] for c in result["candidates"]) == sw["complete_gps"]
    assert len(result["candidates"]) == sw["lgd_taluka_panchayats"]
    assert sum(result["decision_counts"].values()) == len(result["candidates"])
    assert result["decision_counts"]["FROZEN_EXISTING"] == 1


def test_every_stored_decision_follows_the_rules(result):
    for c in result["candidates"]:
        decision, reasons = audit.decide(c, c["tp_code"])
        assert (decision, reasons) == (c["decision"], c["reasons"]), c["tp_name"]


def test_csv_matches_json(result):
    rows = list(csv.DictReader(open(audit.TALUK_CSV_PATH, encoding="utf-8")))
    assert len(rows) == len(result["candidates"])
    by = {c["tp_code"]: c for c in result["candidates"]}
    for row in rows:
        assert row["decision"] == by[row["tp_code"]]["decision"]
        assert int(row["new_cells"]) == by[row["tp_code"]]["grid"]["new_era5_land_cells_vs_yelandur"]


def test_framing_and_forbidden_phrases(result):
    assert "reanalysis proxy — not observation" in result["target_framing"]
    assert "no dataset built" in result["scope"]
    text = json.dumps(result, ensure_ascii=False).lower()
    readme = (audit.OUT_DIR / "README.md").read_text(encoding="utf-8").lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in text and phrase not in readme, phrase


def test_outputs_written_only_inside_stage4_folder():
    assert audit.RESULTS_PATH.parent.name == "stage4_spatial_generalization"
    assert audit.TALUK_CSV_PATH.parent.name == "stage4_spatial_generalization"
