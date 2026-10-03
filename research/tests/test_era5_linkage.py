"""
Validates the Phase 2C Yelandur ERA5-Land spatial-linkage layer
(research/era5_linkage/yelandur_era5_linkage.json).

Two kinds of tests:
  - CONTRACT tests against the COMMITTED layer (same convention as
    test_spatial_proxy.py / test_elevation.py) -- these hold regardless of
    whether real ERA5-Land grid data was available when the layer was built
    (acquisition_status may legitimately be "BLOCKED"; see README.md).
  - REAL, deterministic unit tests of era5_linkage.linkage's pure functions
    against research/synthetic_fixtures.py's existing 0.1-degree fixture
    grid (the same fixture test_coordinates.py already uses) -- these prove
    the actual linkage logic is correct even while Yelandur-specific
    acquisition itself is credential-blocked.
"""

import math

import pytest

from era5_linkage import linkage
from era5_linkage.era5_linkage_data import get_panchayat, get_panchayats, load_layer
from spatial_proxy.spatial_proxy_data import load_layer as load_spatial_proxy
from synthetic_fixtures import make_synthetic_era5_dataset

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


@pytest.fixture(scope="module")
def fixture_grid():
    return make_synthetic_era5_dataset()


# ---------------------------------------------------------------------
# Contract tests (committed layer)
# ---------------------------------------------------------------------

# 1. Exactly 12 expected Yelandur GPs.
def test_exactly_12_expected_gps(panchayats):
    assert len(panchayats) == 12
    assert {gp["gp_name"] for gp in panchayats} == EXPECTED_GP_NAMES


# 2/3/4. 10 COMPLETE / 1 PARTIAL (Agara) / 1 UNAVAILABLE (Mamballi).
def test_coverage_tally_is_10_1_1(panchayats):
    complete = [gp for gp in panchayats if gp["coverage_status"] == "COMPLETE"]
    partial = [gp for gp in panchayats if gp["coverage_status"] == "PARTIAL"]
    unavailable = [gp for gp in panchayats if gp["coverage_status"] == "UNAVAILABLE"]
    assert len(complete) == 10
    assert len(partial) == 1 and partial[0]["gp_name"] == "Agara"
    assert len(unavailable) == 1 and unavailable[0]["gp_name"] == "Mamballi"


# 5. Mamballi has no centroid linkage.
def test_mamballi_has_no_centroid_linkage(layer):
    mamballi = get_panchayat("Mamballi", layer)
    assert mamballi["coverage_status"] == "UNAVAILABLE"
    assert mamballi["centroid_latitude"] is None
    assert mamballi["centroid_longitude"] is None
    assert mamballi["nearest_grid_latitude"] is None
    assert mamballi["nearest_grid_longitude"] is None
    assert mamballi["centroid_to_grid_distance_km"] is None


# 6. Mamballi has no intersecting cells.
def test_mamballi_has_no_intersecting_cells(layer):
    mamballi = get_panchayat("Mamballi", layer)
    assert mamballi["intersecting_cell_count"] is None
    assert mamballi["intersecting_cells"] is None
    assert mamballi["linkage_status"] == "UNAVAILABLE"


# 7. Agara only uses its available geometry.
def test_agara_uses_only_available_geometry(layer, spatial_proxy_layer):
    agara = get_panchayat("Agara", layer)
    assert agara["coverage_status"] == "PARTIAL"
    proxy_agara = next(gp for gp in spatial_proxy_layer["panchayats"] if gp["panchayat_name"] == "Agara")
    # centroid must be the SAME as the spatial proxy's own (partial-geometry) centroid -- not recomputed
    assert agara["centroid_latitude"] == proxy_agara["centroid_wgs84"]["lat"]
    assert agara["centroid_longitude"] == proxy_agara["centroid_wgs84"]["lon"]
    assert "partial" in agara["note"].lower()


# 8. GP IDs are the join key.
def test_gp_ids_are_the_join_key(panchayats, spatial_proxy_layer):
    codes = [gp["panchayat_lgd_code"] for gp in panchayats]
    assert all(isinstance(c, str) and c.isdigit() for c in codes)
    assert len(codes) == len(set(codes))
    proxy_code_by_name = {gp["panchayat_name"]: gp["panchayat_lgd_code"] for gp in spatial_proxy_layer["panchayats"]}
    for gp in panchayats:
        assert gp["panchayat_lgd_code"] == proxy_code_by_name[gp["gp_name"]]


# 9. No fuzzy matching.
def test_no_fuzzy_matching(panchayats, spatial_proxy_layer):
    proxy_status_by_code = {gp["panchayat_lgd_code"]: gp["geometry_status"] for gp in spatial_proxy_layer["panchayats"]}
    for gp in panchayats:
        assert gp["coverage_status"] == proxy_status_by_code[gp["panchayat_lgd_code"]]


# 12. Intersecting cell count is consistent with the stored cell list.
def test_intersecting_cell_count_matches_list_length(panchayats):
    for gp in panchayats:
        if gp["intersecting_cells"] is not None:
            assert gp["intersecting_cell_count"] == len(gp["intersecting_cells"])
        else:
            assert gp["intersecting_cell_count"] is None


# 11 (contract half) + general no-fabrication check: any non-null distance is finite and non-negative.
def test_distances_finite_and_nonnegative_where_present(panchayats):
    for gp in panchayats:
        d = gp["centroid_to_grid_distance_km"]
        if d is not None:
            assert math.isfinite(d)
            assert d >= 0.0


def test_terminology_no_forbidden_phrases(layer):
    import json

    from era5_linkage.era5_linkage_data import LAYER_PATH

    raw_text = LAYER_PATH.read_text(encoding="utf-8").lower()
    forbidden = [
        "current gp boundar", "current panchayat boundar", "official current gp",
        "current gp polygon", "official gp boundar", "official gp polygon",
        "current panchayat polygon", "panchayat-level forecast", "observed weather",
    ]
    for term in forbidden:
        assert term not in raw_text, f"forbidden terminology found: '{term}'"
    assert "historical village-union spatial proxy" in raw_text
    assert "reanalysis" in raw_text
    json.loads(raw_text)


def test_acquisition_status_and_blocker_are_honest(layer):
    assert layer["acquisition_status"] in ("AVAILABLE", "BLOCKED")
    if layer["acquisition_status"] == "BLOCKED":
        assert layer["acquisition_blocker"]  # non-empty explanation
        # every available GP must reflect the blocker, never fabricate a grid link
        for gp in layer["panchayats"]:
            if gp["coverage_status"] != "UNAVAILABLE":
                assert gp["linkage_status"] in ("BLOCKED_NO_ERA5_GRID_DATA", "SINGLE_CELL", "MULTI_CELL", "NO_INTERSECTION")
                if gp["linkage_status"] == "BLOCKED_NO_ERA5_GRID_DATA":
                    assert gp["nearest_grid_latitude"] is None
                    assert gp["centroid_to_grid_distance_km"] is None
    else:
        assert layer["acquisition_blocker"] is None


def test_spatial_variation_audit_present_and_honest(layer):
    audit = layer["spatial_variation_audit"]
    assert audit["available_gp_count"] == 11
    assert audit["complete_gp_count"] == 10
    assert math.isfinite(audit["centroid_latitude_extent_deg"])
    assert math.isfinite(audit["centroid_longitude_extent_deg"])
    assert audit["elevation_mean_range_across_complete_gps"]["n_gps"] == 10
    grid_dist = audit["era5_grid_cell_distribution"]
    assert grid_dist["status"] in ("COMPUTED", "BLOCKED_NO_ERA5_GRID_DATA")
    if grid_dist["status"] == "BLOCKED_NO_ERA5_GRID_DATA":
        assert grid_dist["distinct_cell_count"] is None
        assert grid_dist["all_gps_collapse_onto_one_cell"] is None


# grid_metadata must describe the SAME grid the linkage was computed on --
# never a different location's reference grid (regression: it once described
# the Bangalore pilot grid while acquisition_status was AVAILABLE).
def test_grid_metadata_matches_acquisition_status(layer):
    meta = layer["grid_metadata"]
    assert meta["acquisition_status"] == layer["acquisition_status"]
    assert meta["source_dataset"] == "reanalysis-era5-land"
    grid_fields = ["n_latitude", "n_longitude", "latitude_min", "latitude_max",
                   "longitude_min", "longitude_max", "latitude_order", "longitude_order",
                   "latitude_spacing_deg", "longitude_spacing_deg", "source_file", "source_file_sha256"]
    if layer["acquisition_status"] == "BLOCKED":
        assert all(meta[f] is None for f in grid_fields)
    else:
        assert all(meta[f] is not None for f in grid_fields)
        assert "yelandur" in meta["source_file"].lower()


def test_grid_metadata_has_no_reference_grid_substitution(layer):
    import json

    text = json.dumps(layer["grid_metadata"]).lower()
    for stale in ("pilot", "bangalore", "different location", "reference_file", "reference grid"):
        assert stale not in text, f"stale reference-grid wording in grid_metadata: '{stale}'"


def test_grid_metadata_consistent_with_linked_cells(layer):
    meta = layer["grid_metadata"]
    if layer["acquisition_status"] != "AVAILABLE":
        pytest.skip("no acquired grid")
    # counts agree with extent / spacing
    lat_span = meta["latitude_max"] - meta["latitude_min"]
    lon_span = meta["longitude_max"] - meta["longitude_min"]
    assert round(lat_span / meta["latitude_spacing_deg"]) + 1 == meta["n_latitude"]
    assert round(lon_span / meta["longitude_spacing_deg"]) + 1 == meta["n_longitude"]
    # every stored grid coordinate and every available centroid lies inside the described grid
    for gp in layer["panchayats"]:
        if gp["coverage_status"] == "UNAVAILABLE":
            continue
        cells = [(gp["nearest_grid_latitude"], gp["nearest_grid_longitude"])]
        cells += [(c["latitude"], c["longitude"]) for c in gp["intersecting_cells"]]
        for lat, lon in cells:
            assert meta["latitude_min"] <= lat <= meta["latitude_max"]
            assert meta["longitude_min"] <= lon <= meta["longitude_max"]
        assert meta["latitude_min"] <= gp["centroid_latitude"] <= meta["latitude_max"]
        assert meta["longitude_min"] <= gp["centroid_longitude"] <= meta["longitude_max"]


def test_grid_metadata_matches_local_acquired_file_when_present(layer):
    """The raw NetCDF is gitignored, so this only runs where it exists."""
    import hashlib

    from era5_linkage.build import YELANDUR_RAW_PATH

    if layer["acquisition_status"] != "AVAILABLE" or not YELANDUR_RAW_PATH.exists():
        pytest.skip("acquired Yelandur NetCDF not present locally")
    import xarray as xr

    meta = layer["grid_metadata"]
    assert meta["source_file_sha256"] == hashlib.sha256(YELANDUR_RAW_PATH.read_bytes()).hexdigest()
    with xr.open_dataset(YELANDUR_RAW_PATH) as ds:
        expected = linkage.describe_grid(ds["latitude"].values, ds["longitude"].values)
    for key, value in expected.items():
        assert meta[key] == value, key


# 17/18. Existing spatial proxy / elevation data untouched.
def test_upstream_layers_not_modified(spatial_proxy_layer):
    summary = spatial_proxy_layer["coverage_summary"]
    assert summary == {
        "expected_gp_count": 12, "expected_village_count": 28, "matched_village_count": 26,
        "complete_gp_count": 10, "partial_gp_count": 1, "unavailable_gp_count": 1,
    }


# 16/17/18. Existing modules remain importable (full-suite pass is the authoritative check).
def test_upstream_modules_still_importable():
    import pilot_points  # noqa: F401
    from elevation.elevation_data import load_layer as load_elev  # noqa: F401
    from era5_land import acquire, archive  # noqa: F401
    from pipeline import coordinates, normalize, training_pairs, units  # noqa: F401

    assert pilot_points.RESEARCH_BLOCK["block_id"]


# ---------------------------------------------------------------------
# Real unit tests of linkage.py's pure functions (fixture grid)
# ---------------------------------------------------------------------

# 14. Latitude/longitude ordering is explicit and tested.
def test_grid_ordering_explicit(fixture_grid):
    desc = linkage.describe_grid(fixture_grid["latitude"].values, fixture_grid["longitude"].values)
    assert desc["latitude_order"] == "descending"  # fixture: [13.5, 13.4]
    assert desc["longitude_order"] == "ascending"  # fixture: [77.7, 77.8]
    assert desc["latitude_spacing_deg"] == pytest.approx(0.1)
    assert desc["longitude_spacing_deg"] == pytest.approx(0.1)


# 10 + 13. Nearest grid cell / every stored grid coordinate actually exists in the source grid.
def test_nearest_grid_cell_exists_in_source_grid(fixture_grid):
    lat_values = fixture_grid["latitude"].values
    lon_values = fixture_grid["longitude"].values
    result = linkage.nearest_grid_cell(fixture_grid, 13.43, 77.72)
    assert result["nearest_grid_latitude"] in lat_values
    assert result["nearest_grid_longitude"] in lon_values


# 11. Distance values are finite and non-negative (real function test).
def test_nearest_grid_cell_distance_finite_nonnegative(fixture_grid):
    result = linkage.nearest_grid_cell(fixture_grid, 13.43, 77.72)
    assert math.isfinite(result["centroid_to_grid_distance_km"])
    assert result["centroid_to_grid_distance_km"] >= 0.0
    assert math.isfinite(result["latitude_difference_deg"])
    assert math.isfinite(result["longitude_difference_deg"])


# 15. Grid-cell construction is deterministic.
def test_cell_polygon_construction_is_deterministic(fixture_grid):
    lat_values = fixture_grid["latitude"].values
    lon_values = fixture_grid["longitude"].values
    poly_a = linkage.build_cell_polygon(lat_values, lon_values, 0, 0)
    poly_b = linkage.build_cell_polygon(lat_values, lon_values, 0, 0)
    assert poly_a.equals(poly_b)
    assert poly_a.bounds == poly_b.bounds


def test_cell_polygon_covers_expected_extent(fixture_grid):
    lat_values = fixture_grid["latitude"].values  # [13.5, 13.4]
    lon_values = fixture_grid["longitude"].values  # [77.7, 77.8]
    # interior-style outermost cell (only 2 points on each axis, both are "outermost"):
    # cell (13.5, 77.7) should be centered there with 0.1-degree half-widths mirrored outward.
    poly = linkage.build_cell_polygon(lat_values, lon_values, 0, 0)
    minx, miny, maxx, maxy = poly.bounds
    assert minx == pytest.approx(77.65)
    assert maxx == pytest.approx(77.75)
    assert miny == pytest.approx(13.45)
    assert maxy == pytest.approx(13.55)


def test_cells_intersecting_geometry_returns_only_real_grid_coordinates(fixture_grid):
    import shapely.geometry as sgeom

    lat_values = fixture_grid["latitude"].values
    lon_values = fixture_grid["longitude"].values
    geom = sgeom.mapping(sgeom.box(77.6, 13.3, 77.9, 13.6))  # covers the whole fixture grid
    hits = linkage.cells_intersecting_geometry(geom, lat_values, lon_values)
    assert len(hits) == 4  # full 2x2 fixture grid
    for hit in hits:
        assert hit["latitude"] in lat_values
        assert hit["longitude"] in lon_values


def test_build_grid_metadata_is_derived_from_given_dataset(fixture_grid, tmp_path):
    """Values come from the dataset passed in (here the 13.4-13.5N fixture),
    proving nothing about Yelandur's grid is hardcoded in the builder."""
    import hashlib

    from era5_linkage.build import build_grid_metadata

    source = tmp_path / "fixture.nc"
    source.write_bytes(b"fixture-bytes")
    meta = build_grid_metadata(fixture_grid, source)
    assert meta["acquisition_status"] == "AVAILABLE"
    assert meta["n_latitude"] == 2 and meta["n_longitude"] == 2
    assert meta["latitude_min"] == pytest.approx(13.4)
    assert meta["latitude_max"] == pytest.approx(13.5)
    assert meta["longitude_min"] == pytest.approx(77.7)
    assert meta["longitude_max"] == pytest.approx(77.8)
    assert meta["latitude_order"] == "descending"
    assert meta["longitude_order"] == "ascending"
    assert meta["latitude_spacing_deg"] == pytest.approx(0.1)
    assert meta["longitude_spacing_deg"] == pytest.approx(0.1)
    assert meta["source_file_sha256"] == hashlib.sha256(b"fixture-bytes").hexdigest()


def test_build_grid_metadata_blocked_is_all_null():
    from era5_linkage.build import build_grid_metadata

    meta = build_grid_metadata(None)
    assert meta["acquisition_status"] == "BLOCKED"
    assert meta["source_file"] is None
    for key in ("n_latitude", "n_longitude", "latitude_min", "latitude_max", "longitude_min",
                "longitude_max", "latitude_order", "longitude_order",
                "latitude_spacing_deg", "longitude_spacing_deg", "source_file_sha256"):
        assert meta[key] is None


def test_cells_intersecting_geometry_empty_when_outside_grid(fixture_grid):
    import shapely.geometry as sgeom

    lat_values = fixture_grid["latitude"].values
    lon_values = fixture_grid["longitude"].values
    far_away = sgeom.mapping(sgeom.box(10.0, 5.0, 10.1, 5.1))
    hits = linkage.cells_intersecting_geometry(far_away, lat_values, lon_values)
    assert hits == []
