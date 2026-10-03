"""
Stage 4A/4B design (research/stage4_spatial_generalization/{regimes,selection,
folds,land_sea,design}.py) and the committed stage4_acquisition_manifest.json.
"""

import json
import random

import pytest

from stage4_spatial_generalization import audit, design, folds, grid, land_sea, selection
from stage4_spatial_generalization.regimes import REGIMES, TALUKA_OVERRIDES, ZILA_DEFAULT, regime_of

FORBIDDEN_PHRASES = ["ground truth", "observed panchayat weather", "validated panchayat forecast",
                     "accurate panchayat weather", "actual panchayat weather prediction"]


# ---------------------------------------------------------------------
# Selection unit tests (synthetic)
# ---------------------------------------------------------------------

def _cand(code, regime, zp, lat, lon, n_cells=8, share=0.9):
    cells = {grid.era5_land_cell(lat + 0.1 * (i % 3), lon + 0.1 * (i // 3)) for i in range(n_cells)}
    return {"tp_code": code, "tp_name": f"T{code}", "zp_code": zp, "zp_name": f"Z{zp}", "regime": regime,
            "centroid": (lat + 0.1, lon + 0.1), "cells": cells, "complete_share": share}


REF = {"centroid": (12.05, 77.1), "cells": {(12.0, 77.1), (12.1, 77.1)}}


def _pool():
    pool = []
    for i, regime in enumerate(REGIMES):
        pool.append(_cand(f"{i}1", regime, f"z{i}a", 13.0 + i, 74.5))
        pool.append(_cand(f"{i}2", regime, f"z{i}b", 13.0 + i, 76.5))
        pool.append(_cand(f"{i}3", regime, f"z{i}c", 13.0 + i, 75.5, n_cells=5))   # too few cells
        pool.append(_cand(f"{i}4", regime, f"z{i}a", 13.5 + i, 77.5))              # same Zila as {i}1
    return pool


def test_selection_is_deterministic_and_input_order_independent():
    pool = _pool()
    a, log_a = selection.select(pool, REF)
    shuffled = pool[:]
    random.Random(7).shuffle(shuffled)
    b, log_b = selection.select(shuffled, REF)
    assert [s["tp_code"] for s in a] == [s["tp_code"] for s in b]
    assert log_a == log_b


def test_selection_respects_constraints_and_covers_regimes():
    sel, _ = selection.select(_pool(), REF)
    assert {s["regime"] for s in sel} == set(REGIMES)
    assert len({s["zp_code"] for s in sel}) == len(sel)
    assert all(len(s["cells"]) >= selection.MIN_NEW_CELLS for s in sel)
    for i, s in enumerate(sel):
        assert selection.min_cell_separation(s["cells"], REF["cells"]) >= selection.MIN_SEPARATION_CELLS
        for t in sel[i + 1:]:
            assert selection.min_cell_separation(s["cells"], t["cells"]) >= selection.MIN_SEPARATION_CELLS
    assert max(sum(1 for s in sel if s["regime"] == r) for r in REGIMES) <= selection.PER_REGIME


def test_maximin_prefers_distant_candidate_not_larger_one():
    near_big = _cand("A", REGIMES[0], "za", 12.8, 77.6, n_cells=9)
    far_small = _cand("B", REGIMES[0], "zb", 17.0, 75.0, n_cells=6)
    sel, _ = selection.select([near_big, far_small], REF)
    assert sel[0]["tp_code"] == "B"


def test_regime_without_valid_candidate_is_logged_not_filled():
    _, log = selection.select([_cand("A", REGIMES[0], "za", 15.0, 75.0)], REF)
    assert any(entry["picked"] is None and entry["regime"] == REGIMES[1] for entry in log)


# ---------------------------------------------------------------------
# Fold unit tests
# ---------------------------------------------------------------------

def test_fold_builders_separate_geography():
    sel = {s["tp_code"]: s for s in selection.select(_pool(), REF)[0]}
    for f in folds.taluka_holdout(sel) + folds.grouped_holdout(sel, "regime", "regime"):
        assert not set(f["test_taluka_panchayats"]) & set(f["train_taluka_panchayats"])
        assert f["shared_cells"] == 0
        assert f["min_test_train_separation_cells"] >= selection.MIN_SEPARATION_CELLS
    for f in folds.cell_group_diagnostic(sel):
        assert f["min_test_train_separation_cells"] > folds.BUFFER_CELLS


def test_block_assignment():
    assert folds.block_of((12.0, 77.1)) == folds.block_of((12.2, 77.1))
    assert folds.block_of((12.0, 77.1)) != folds.block_of((12.3, 77.1))


# ---------------------------------------------------------------------
# Regimes and land/sea
# ---------------------------------------------------------------------

def test_regime_map_covers_every_zila_and_overrides_are_real():
    result = json.loads(audit.RESULTS_PATH.read_text(encoding="utf-8"))
    zps = {c["zp_name"] for c in result["candidates"]}
    assert zps == set(ZILA_DEFAULT)
    names = {(c["zp_name"], c["tp_name"]) for c in result["candidates"]}
    assert set(TALUKA_OVERRIDES) <= names
    assert set(ZILA_DEFAULT.values()) | set(TALUKA_OVERRIDES.values()) == set(REGIMES)
    with pytest.raises(KeyError):
        regime_of("Nowhere", "X")


def test_land_sea_resolution_rule():
    flagged = {"1": ["E5L_12.00N_74.50E"], "2": ["E5L_13.00N_74.60E", "E5L_13.10N_74.60E"]}
    assert land_sea.resolve(flagged, None)["1"]["status"] == "UNRESOLVED_PENDING_MASK"
    mask = {"E5L_12.00N_74.50E": True, "E5L_13.00N_74.60E": True, "E5L_13.10N_74.60E": False}
    out = land_sea.resolve(flagged, mask)
    assert out["1"]["status"] == "RESOLVED_LAND"
    assert out["2"]["status"] == "NON_LAND_CELLS" and out["2"]["non_land_cells"] == ["E5L_13.10N_74.60E"]
    with pytest.raises(KeyError):
        land_sea.resolve({"3": ["E5L_15.00N_74.00E"]}, mask)


def test_mask_request_covers_cells_and_is_tiny():
    req = land_sea.mask_request({(12.0, 74.5), (13.1, 78.0)})
    n, w, s, e = req["request"]["area"]
    assert (n, w, s, e) == (13.2, 74.4, 11.9, 78.1)
    assert req["request"]["time"] == ["00:00"] and len(req["request"]["variable"]) == 1
    assert req["performed_in_this_stage"] is False


def test_parse_cell_id_roundtrip():
    for c in [(12.0, 77.1), (17.9, 74.0), (12.0, 77.19999999999999)]:
        assert grid.parse_cell_id(grid.cell_id(c)) == pytest.approx(c)


# ---------------------------------------------------------------------
# Contract tests on the committed manifest
# ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def manifest():
    if not design.MANIFEST_PATH.exists():
        pytest.skip("stage4_acquisition_manifest.json not generated")
    return json.loads(design.MANIFEST_PATH.read_text(encoding="utf-8"))


def test_selected_count_and_regime_coverage(manifest):
    sel = manifest["selected"]
    assert 10 <= len(sel) <= 15 and manifest["selected_count"] == len(sel)
    assert {e["geographic_regime"] for e in sel} == set(REGIMES)
    assert all(len(v) >= 1 for v in manifest["selected_regime_coverage"].values())
    assert len({e["zp_code"] for e in sel}) == len(sel)
    for e in sel:
        assert e["geographic_regime"] == regime_of(e["zp_name"], e["tp_name"])


def test_only_recommended_candidates_selected_and_yelandur_frozen(manifest):
    result = json.loads(audit.RESULTS_PATH.read_text(encoding="utf-8"))
    decision = {c["tp_code"]: c["decision"] for c in result["candidates"]}
    assert all(decision[e["tp_code"]] == "RECOMMEND_FOR_SHORTLIST" for e in manifest["selected"])
    assert "6132" not in {e["tp_code"] for e in manifest["selected"]}
    for kind in ("taluka_holdout", "regional_holdout"):
        for f in manifest["fold_design"][kind]:
            assert "6132" not in f["train_taluka_panchayats"] + f["test_taluka_panchayats"]


def test_every_taluka_panchayat_accounted_for_exactly_once(manifest):
    result = json.loads(audit.RESULTS_PATH.read_text(encoding="utf-8"))
    codes = [e["tp_code"] for e in manifest["selected"]] + [x["tp_code"] for x in manifest["exclusions"]]
    assert sorted(codes) == sorted(c["tp_code"] for c in result["candidates"])
    assert all(x["reasons"] for x in manifest["exclusions"])
    cats = {x["category"] for x in manifest["exclusions"]}
    assert cats <= {"FROZEN_REFERENCE", "AUDIT_EXCLUDE", "CONDITIONAL_UNRESOLVED_PENDING_LAND_SEA_MASK", "ELIGIBLE_NOT_SELECTED"}


def test_expected_cells_match_listed_gps(manifest):
    for e in manifest["selected"]:
        from_gps = sorted({g["era5_land_cell"] for g in e["spatial_proxy"]["complete_gps"]})
        assert from_gps == e["expected_era5_land_cells"]
        assert e["spatial_proxy"]["complete_gps"]
        n, w, s, east = e["era5_land_request_area_nwse"]
        for cid in e["expected_era5_land_cells"]:
            lat, lon = grid.parse_cell_id(cid)
            assert s <= lat <= n and w <= lon <= east
        # ERA5 area must contain all 4 bilinear corners of every expected target cell
        n2, w2, s2, e2 = e["era5_request_area_nwse"]
        for cid in e["expected_era5_land_cells"]:
            box_lat, box_lon = grid.enclosing_era5_box(grid.parse_cell_id(cid))
            assert s2 <= box_lat and box_lat + grid.ERA5_SPACING <= n2
            assert w2 <= box_lon and box_lon + grid.ERA5_SPACING <= e2
        assert all(t.startswith("Copernicus_DSM_COG_10_") for t in e["elevation"]["glo30_tiles_required"])


def _cells_of(manifest, codes):
    by = {e["tp_code"]: e for e in manifest["selected"]}
    return {grid.parse_cell_id(c) for code in codes for c in by[code]["expected_era5_land_cells"]}


def _gps_of(manifest, codes):
    by = {e["tp_code"]: e for e in manifest["selected"]}
    return {g["gp_code"] for code in codes for g in by[code]["spatial_proxy"]["complete_gps"]}


def test_no_overlap_between_train_and_test_geography(manifest):
    fd = manifest["fold_design"]
    for kind in ("taluka_holdout", "regional_holdout"):
        for f in fd[kind]:
            test, train = f["test_taluka_panchayats"], f["train_taluka_panchayats"]
            assert test and train and not set(test) & set(train)
            assert set(test) | set(train) == {e["tp_code"] for e in manifest["selected"]}
            tc, rc = _cells_of(manifest, test), _cells_of(manifest, train)
            assert not tc & rc
            assert not _gps_of(manifest, test) & _gps_of(manifest, train)
            sep = min(grid.chebyshev_cells(a, b) for a in tc for b in rc)
            assert sep >= selection.MIN_SEPARATION_CELLS and sep == f["min_test_train_separation_cells"]
    assert fd["district_holdout"]["equivalent_to"] == "taluka_holdout"
    assert len(fd["taluka_holdout"]) == len(manifest["selected"])
    assert len(fd["regional_holdout"]) == len({e["geographic_regime"] for e in manifest["selected"]})


def test_cell_diagnostic_folds_partition_cells_with_buffer(manifest):
    diag = manifest["fold_design"]["cell_group_diagnostic"]
    assert "DIAGNOSTIC ONLY" in diag["label"]
    all_cells = set().union(*({grid.parse_cell_id(c) for c in e["expected_era5_land_cells"]} for e in manifest["selected"]))
    tested = []
    for f in diag["folds"]:
        test = {grid.parse_cell_id(c) for c in f["test_cells"]}
        buffer = {grid.parse_cell_id(c) for c in f["buffer_cells_excluded_from_training"]}
        train = all_cells - test - buffer
        assert not test & buffer
        assert min(grid.chebyshev_cells(a, b) for a in test for b in train) > diag["buffer_cells"]
        tested += list(test)
    assert sorted(tested) == sorted(all_cells)  # each cell tested exactly once


def test_temporal_split_is_blocked_not_random(manifest):
    t = manifest["fold_design"]["temporal_split"]
    assert t["train_period_utc"][1] < t["embargo_utc"][0] < t["test_period_utc"][0]
    assert "random" not in json.dumps(manifest["fold_design"]).lower()


def test_land_sea_section(manifest):
    ls = manifest["land_sea_4a"]
    assert "NOT RESOLVABLE OFFLINE" in ls["offline_status"]
    assert ls["conditional_taluka_panchayats"] == 31 == len(ls["resolution"])
    assert all(r["status"] == "UNRESOLVED_PENDING_MASK" for r in ls["resolution"].values())
    req = ls["required_acquisition"]
    assert req["performed_in_this_stage"] is False and req["dataset"] == "reanalysis-era5-land"
    n, w, s, e = req["request"]["area"]
    for entry in manifest["selected"]:
        for cid in entry["expected_era5_land_cells"]:
            lat, lon = grid.parse_cell_id(cid)
            assert s <= lat <= n and w <= lon <= e
    for r in ls["resolution"].values():
        for cid in r["flagged_cells"]:
            lat, lon = grid.parse_cell_id(cid)
            assert s <= lat <= n and w <= lon <= e


def test_previous_artifacts_preserved(manifest):
    for key, path in design.PROTECTED_ARTIFACTS.items():
        assert audit.sha256(path) == manifest["protected_artifact_sha256"][key], key


def test_framing_and_forbidden_phrases(manifest):
    assert "reanalysis proxy — not observation" in manifest["target_framing"]
    text = json.dumps(manifest, ensure_ascii=False).lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in text, phrase


def _without_disk_snapshot(m: dict) -> dict:
    """Drop fields that record which GLO-30 tiles were on disk at design
    time (a snapshot of local state, not a design decision): they change
    legitimately once Stage 4C downloads the tiles."""
    m = json.loads(json.dumps(m))
    for e in m["selected"]:
        e["elevation"].pop("already_on_disk")
        e["elevation"].pop("to_download")
    m["selected_totals"].pop("glo30_tiles_to_download")
    return m


def test_manifest_rebuild_is_deterministic(manifest):
    if not audit.SOURCES["datameet_ka_geojson"].exists():
        pytest.skip("raw DataMeet source not present locally")
    rebuilt = json.loads(json.dumps(design.build(), ensure_ascii=False))
    assert _without_disk_snapshot(rebuilt) == _without_disk_snapshot(manifest)
    # the snapshot fields may only change because the listed tiles now exist locally
    for old, new in zip(manifest["selected"], rebuilt["selected"]):
        assert set(old["elevation"]["already_on_disk"]) <= set(new["elevation"]["already_on_disk"])
        assert set(new["elevation"]["already_on_disk"]) | set(new["elevation"]["to_download"]) == \
            set(old["elevation"]["glo30_tiles_required"])
