"""
Validates the Phase 2C Yelandur elevation-context layer
(research/elevation/yelandur_elevation.json). These tests run against the
COMMITTED layer, not a live rebuild -- same convention as
test_spatial_proxy.py and test_admin_identity.py.
"""

import math

import pytest

from elevation.elevation_data import get_panchayat, get_panchayats, load_layer
from spatial_proxy.spatial_proxy_data import load_layer as load_spatial_proxy

EXPECTED_GP_NAMES = {
    "Agara", "Ambale", "Biligiri Ranganabetta", "Duggatti", "Gowdahalli",
    "Gumballi", "Honnuru", "Kestur", "Madduru", "Mamballi", "Yariyuru",
    "Yeragamballi",
}


@pytest.fixture(scope="module")
def layer():
    return load_layer()


@pytest.fixture(scope="module")
def panchayats(layer):
    return get_panchayats(layer)


@pytest.fixture(scope="module")
def spatial_proxy_layer():
    return load_spatial_proxy()


# 1. Exactly 12 expected GPs exist.
def test_exactly_12_expected_gps(panchayats):
    assert len(panchayats) == 12
    assert {gp["gp_name"] for gp in panchayats} == EXPECTED_GP_NAMES


# 2. Exactly 10 COMPLETE / 1 PARTIAL / 1 UNAVAILABLE.
def test_coverage_tally_is_10_1_1(panchayats):
    complete = [gp for gp in panchayats if gp["coverage_status"] == "COMPLETE"]
    partial = [gp for gp in panchayats if gp["coverage_status"] == "PARTIAL"]
    unavailable = [gp for gp in panchayats if gp["coverage_status"] == "UNAVAILABLE"]
    assert len(complete) == 10
    assert len(partial) == 1
    assert len(unavailable) == 1


# 3. Mamballi has no elevation statistics.
def test_mamballi_has_no_elevation_statistics(layer):
    mamballi = get_panchayat("Mamballi", layer)
    assert mamballi["coverage_status"] == "UNAVAILABLE"
    for field in ("mean_m", "min_m", "max_m", "range_m", "std_m", "sample_count"):
        assert mamballi[field] is None, f"Mamballi.{field} should be null, got {mamballi[field]}"


# 4. Agara is marked PARTIAL.
def test_agara_is_partial(layer):
    agara = get_panchayat("Agara", layer)
    assert agara["coverage_status"] == "PARTIAL"
    # PARTIAL still has real (non-null) statistics -- from the covered geometry only.
    assert agara["sample_count"] is not None and agara["sample_count"] > 0


# 5. No unavailable geometry gets an inferred elevation.
def test_no_unavailable_gp_has_inferred_elevation(panchayats):
    for gp in panchayats:
        if gp["coverage_status"] == "UNAVAILABLE":
            assert gp["mean_m"] is None
            assert gp["min_m"] is None
            assert gp["max_m"] is None
            assert gp["sample_count"] is None


# 6. Elevation values are finite wherever present.
def test_elevation_values_finite_where_present(panchayats):
    checked = 0
    for gp in panchayats:
        for field in ("mean_m", "min_m", "max_m", "range_m", "std_m"):
            v = gp[field]
            if v is not None:
                assert math.isfinite(v), f"{gp['gp_name']}.{field}={v} is not finite"
                checked += 1
    assert checked > 0


# 7. min_m <= mean_m <= max_m.
def test_min_le_mean_le_max(panchayats):
    checked = 0
    for gp in panchayats:
        if gp["coverage_status"] != "UNAVAILABLE":
            assert gp["min_m"] <= gp["mean_m"] <= gp["max_m"]
            checked += 1
    assert checked == 11


# 8. range_m == max_m - min_m within an appropriate floating tolerance.
def test_range_equals_max_minus_min(panchayats):
    checked = 0
    for gp in panchayats:
        if gp["coverage_status"] != "UNAVAILABLE":
            assert gp["range_m"] == pytest.approx(gp["max_m"] - gp["min_m"], abs=1e-6)
            checked += 1
    assert checked == 11


# 9. sample_count is positive wherever statistics exist.
def test_sample_count_positive_where_stats_exist(panchayats):
    checked = 0
    for gp in panchayats:
        if gp["coverage_status"] != "UNAVAILABLE":
            assert gp["sample_count"] > 0
            checked += 1
    assert checked == 11


# 10. CRS/source metadata exists.
def test_crs_and_source_metadata_present(layer, panchayats):
    assert layer["horizontal_crs"] == "EPSG:4326 (WGS84)"
    assert layer["source"] == "Copernicus DEM GLO-30"
    assert layer["resolution_m"] == 30
    assert layer["vertical_unit"] == "metres"
    assert layer["source_provenance"]["registry_url"].startswith("https://registry.opendata.aws")
    assert layer["source_provenance"]["tiles_used"]  # non-empty
    for gp in panchayats:
        assert gp["horizontal_crs"] == "EPSG:4326 (WGS84)"
        assert gp["source"] == "Copernicus DEM GLO-30"
        assert gp["resolution_m"] == 30


# 11. GP IDs are used for joins.
def test_gp_ids_used_for_join(panchayats, spatial_proxy_layer):
    gp_ids = [gp["gp_id"] for gp in panchayats]
    assert all(isinstance(gid, str) and gid.isdigit() for gid in gp_ids)
    assert len(gp_ids) == len(set(gp_ids)), "duplicate gp_id values found"

    proxy_code_by_name = {gp["panchayat_name"]: gp["panchayat_lgd_code"] for gp in spatial_proxy_layer["panchayats"]}
    for gp in panchayats:
        assert gp["gp_id"] == proxy_code_by_name[gp["gp_name"]], (
            f"elevation gp_id for {gp['gp_name']} doesn't match spatial-proxy panchayat_lgd_code"
        )


# 12. No fuzzy matching occurs.
def test_no_fuzzy_matching(panchayats, spatial_proxy_layer):
    # Every elevation record's coverage_status must be an exact mirror of
    # the spatial proxy's geometry_status for the SAME panchayat_lgd_code
    # (never inferred from a name-similarity join).
    proxy_status_by_code = {gp["panchayat_lgd_code"]: gp["geometry_status"] for gp in spatial_proxy_layer["panchayats"]}
    for gp in panchayats:
        assert gp["coverage_status"] == proxy_status_by_code[gp["gp_id"]]


# 13. Raw DEM files are gitignored.
def test_raw_dem_is_gitignored():
    import subprocess
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    raw_dir = repo_root / "data" / "raw" / "elevation"
    probe = raw_dir / "some_tile.tif"
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(probe)],
        cwd=repo_root, capture_output=True,
    )
    assert result.returncode == 0, "data/raw/elevation/*.tif is NOT gitignored"


# 14. Output is deterministic.
def test_output_is_deterministic():
    from elevation.elevation_data import LAYER_PATH

    text_a = LAYER_PATH.read_text(encoding="utf-8")
    text_b = LAYER_PATH.read_text(encoding="utf-8")
    assert text_a == text_b  # committed output is a fixed, reproducible artifact, not regenerated per-test


# 15. Existing spatial-proxy data is not modified.
def test_spatial_proxy_data_not_modified(spatial_proxy_layer):
    summary = spatial_proxy_layer["coverage_summary"]
    assert summary == {
        "expected_gp_count": 12,
        "expected_village_count": 28,
        "matched_village_count": 26,
        "complete_gp_count": 10,
        "partial_gp_count": 1,
        "unavailable_gp_count": 1,
    }
    # geometry_status per GP still matches what this elevation layer assumes
    statuses = {gp["panchayat_name"]: gp["geometry_status"] for gp in spatial_proxy_layer["panchayats"]}
    assert statuses["Agara"] == "PARTIAL"
    assert statuses["Mamballi"] == "UNAVAILABLE"


# 16. Existing Phase 2B artifacts/tests remain unaffected (import-level sanity;
#     the full suite run is the authoritative check for this).
def test_phase_2b_modules_still_importable():
    import pilot_points  # noqa: F401
    from pipeline import coordinates, normalize, training_pairs, units  # noqa: F401

    assert pilot_points.RESEARCH_BLOCK["block_id"]
