"""
Validates the Stage 6 Yelandur historical village-union spatial proxy layer
(research/spatial_proxy/yelandur_spatial_proxy.json). These tests run
against the COMMITTED layer, not a live rebuild -- same convention as
test_admin_identity.py: they check the data that will actually ship.
"""

import math

import pytest
import shapely.geometry as sgeom

from spatial_proxy.spatial_proxy_data import get_panchayat, get_panchayats, load_layer

FORBIDDEN_TERMS = [
    "current gp boundar",
    "current gp polygon",
    "official current gp",
    "current panchayat boundar",
    "current panchayat polygon",
    "official gp boundar",
    "official gp polygon",
]

KARNATAKA_LON_RANGE = (74.0, 78.6)
KARNATAKA_LAT_RANGE = (11.5, 18.5)


@pytest.fixture(scope="module")
def layer():
    return load_layer()


@pytest.fixture(scope="module")
def panchayats(layer):
    return get_panchayats(layer)


def test_exactly_12_gps_represented(panchayats):
    assert len(panchayats) == 12
    names = {gp["panchayat_name"] for gp in panchayats}
    assert names == {
        "Agara", "Ambale", "Biligiri Ranganabetta", "Duggatti", "Gowdahalli",
        "Gumballi", "Honnuru", "Kestur", "Madduru", "Mamballi", "Yariyuru",
        "Yeragamballi",
    }


def test_exactly_10_complete(panchayats):
    complete = [gp for gp in panchayats if gp["geometry_status"] == "COMPLETE"]
    assert len(complete) == 10


def test_exactly_1_partial(panchayats):
    partial = [gp for gp in panchayats if gp["geometry_status"] == "PARTIAL"]
    assert len(partial) == 1
    assert partial[0]["panchayat_name"] == "Agara"


def test_exactly_1_unavailable(panchayats):
    unavailable = [gp for gp in panchayats if gp["geometry_status"] == "UNAVAILABLE"]
    assert len(unavailable) == 1
    assert unavailable[0]["panchayat_name"] == "Mamballi"


def test_26_of_28_villages_matched(panchayats):
    total_expected = sum(gp["expected_village_count"] for gp in panchayats)
    total_matched = sum(gp["matched_village_count"] for gp in panchayats)
    assert total_expected == 28
    assert total_matched == 26


def test_zero_fuzzy_matches(panchayats):
    allowed_methods = {"EXACT_CODE", "EXACT_CROSSWALK", "EXACT_NAME", "UNMATCHED"}
    seen_methods = set()
    for gp in panchayats:
        for v in gp["constituent_villages"]:
            assert v["match_method"] in allowed_methods, f"unexpected method {v['match_method']}"
            assert "FUZZY" not in v["match_method"].upper()
            seen_methods.add(v["match_method"])
    # every real match in this dataset landed in EXACT_CROSSWALK -- confirms
    # no exact-name fallback or fuzzy logic was ever actually exercised
    assert seen_methods == {"EXACT_CROSSWALK", "UNMATCHED"}


def test_zero_duplicate_village_assignments(panchayats):
    all_village_codes = [
        v["village_lgd_code"]
        for gp in panchayats
        for v in gp["constituent_villages"]
    ]
    assert len(all_village_codes) == 28
    assert len(all_village_codes) == len(set(all_village_codes)), "a village is assigned to more than one GP"


def test_every_matched_polygon_linked_through_census_2001_code(panchayats):
    for gp in panchayats:
        for v in gp["constituent_villages"]:
            if v["matched"]:
                assert v["match_method"] == "EXACT_CROSSWALK"
                assert v["census_2001_code"].strip() != ""


def test_every_complete_gp_has_all_expected_villages(panchayats):
    for gp in panchayats:
        if gp["geometry_status"] == "COMPLETE":
            assert gp["matched_village_count"] == gp["expected_village_count"]
            assert gp["missing_village_count"] == 0
            assert all(v["matched"] for v in gp["constituent_villages"])


def test_agara_is_partial_missing_kinakahalli(layer):
    agara = get_panchayat("Agara", layer)
    assert agara["geometry_status"] == "PARTIAL"
    assert agara["missing_villages"] == ["Kinakahalli"]
    assert agara["matched_village_count"] == 1
    assert agara["expected_village_count"] == 2
    assert agara["geometry"] is not None  # partial union IS still stored


def test_mamballi_is_unavailable(layer):
    mamballi = get_panchayat("Mamballi", layer)
    assert mamballi["geometry_status"] == "UNAVAILABLE"
    assert mamballi["matched_village_count"] == 0
    assert mamballi["geometry"] is None
    assert mamballi["centroid_wgs84"] is None
    assert mamballi["area_km2"] is None


def test_no_current_boundary_terminology_in_metadata():
    import json
    from spatial_proxy.spatial_proxy_data import LAYER_PATH

    raw_text = LAYER_PATH.read_text(encoding="utf-8").lower()
    for term in FORBIDDEN_TERMS:
        assert term not in raw_text, f"forbidden current-boundary terminology found: '{term}'"

    # sanity: the allowed proxy terminology IS present
    assert "historical village-union spatial proxy" in raw_text
    assert "1991-vintage spatial proxy derived from village polygons" in raw_text
    json.loads(raw_text)  # still valid JSON after the case-folded read


def test_source_attribution_and_license_present(panchayats, layer):
    for gp in panchayats:
        assert "odbl" in gp["source_license"].lower()
        assert gp["source_blob_sha"].strip() != ""
        assert gp["source_content_commit"].strip() != ""
        assert "1991" in gp["source_positional_error"] or "500m" in gp["source_positional_error"]
    assert "datameet" in layer["source_provenance"]["datameet_repo"].lower()


def test_geometry_validity(panchayats):
    checked = 0
    for gp in panchayats:
        if gp["geometry_status"] != "UNAVAILABLE":
            geom = sgeom.shape(gp["geometry"])
            assert geom.is_valid, f"invalid geometry for GP {gp['panchayat_name']}"
            checked += 1
    assert checked == 11  # 10 COMPLETE + 1 PARTIAL


def test_centroid_coordinates_finite_and_in_expected_range(panchayats):
    checked = 0
    for gp in panchayats:
        centroid = gp["centroid_wgs84"]
        if centroid is None:
            continue
        lon, lat = centroid["lon"], centroid["lat"]
        assert math.isfinite(lon) and math.isfinite(lat)
        assert KARNATAKA_LON_RANGE[0] <= lon <= KARNATAKA_LON_RANGE[1]
        assert KARNATAKA_LAT_RANGE[0] <= lat <= KARNATAKA_LAT_RANGE[1]
        checked += 1
    assert checked == 11
