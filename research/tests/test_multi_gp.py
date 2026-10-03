"""
Phase 2D Yelandur multi-GP dataset (research/multi_gp/).

  - Unit tests of the pure acquisition-window, pairing and split logic
    (always run; no network, no raw files).
  - Contract tests of the committed manifest (always run once built).
  - Contract tests of the gitignored Parquet dataset (skipped where the
    data file has not been regenerated locally).
"""

import json

import numpy as np
import pandas as pd
import pytest

from multi_gp import acquire, pairing, splits
from multi_gp.build import DATASET_PATH, MANIFEST_PATH, SOURCE_NOTE, cell_group_id

FORBIDDEN_TERMS = [
    "ground truth", "observed panchayat weather", "measured panchayat temperature",
    "validated panchayat forecast",
]


# ---------------------------------------------------------------------
# Acquisition window (isolated from the Phase 2A pilot)
# ---------------------------------------------------------------------

def test_window_is_three_full_years():
    months = acquire.window_months()
    assert len(months) == 36
    assert months[0] == (2021, 1) and months[-1] == (2023, 12)
    assert sum(len(acquire.month_days(y, m)) for y, m in months) == 1095


def test_month_days_respect_calendar():
    assert len(acquire.month_days(2021, 2)) == 28
    assert len(acquire.month_days(2024, 2)) == 29
    assert acquire.month_days(2023, 4)[-1] == "30"


def test_era5_land_request_matches_linkage_area_and_pilot_variables():
    from era5_land.acquire import VARIABLES
    from era5_linkage.build import YELANDUR_AREA

    req = acquire.build_era5_land_request(2022, 2)
    assert req["area"] == YELANDUR_AREA
    assert req["variable"] == VARIABLES
    assert req["day"] == [f"{d:02d}" for d in range(1, 29)]
    assert req["time"] == [f"{h:02d}:00" for h in range(24)]
    assert "product_type" not in req


def test_era5_request_is_reanalysis_single_levels():
    req = acquire.build_era5_request(2021, 7)
    assert acquire.ERA5_DATASET == "reanalysis-era5-single-levels"
    assert req["product_type"] == ["reanalysis"]
    assert req["area"] == [12.5, 76.75, 11.75, 77.5]
    # all area edges lie on the native 0.25 deg grid
    assert all((edge * 4) == int(edge * 4) for edge in req["area"])


def test_pilot_acquisition_untouched():
    from era5_land import acquire as pilot

    assert pilot.PILOT_YEAR == "2023" and pilot.PILOT_MONTH == "06"
    assert pilot.PILOT_DAYS == ["01", "02", "03"]
    assert pilot.PILOT_AREA == [13.55, 77.45, 13.30, 77.95]
    assert pilot.build_pilot_request()["day"] == ["01", "02", "03"]


def test_multi_year_paths_never_collide_with_pilot_files():
    from era5_land.acquire import RAW_OUTPUT_DIR

    pilot_files = {RAW_OUTPUT_DIR / "era5_land_pilot_202306.nc", RAW_OUTPUT_DIR / "era5_land_yelandur_202306.nc"}
    paths = {p for _, _, p in acquire.acquisition_jobs()}
    assert len(paths) == 72
    assert not paths & pilot_files
    assert all("multi_gp" in p.parts for p in paths)


def test_member_paths_merges_split_zip_members(tmp_path):
    primary = tmp_path / "era5_yelandur_202101.nc"
    extra = tmp_path / "era5_yelandur_202101__data_stream-oper_stepType-accum.nc"
    unrelated = tmp_path / "era5_yelandur_202102__data_stream-oper_stepType-accum.nc"
    for p in (primary, extra, unrelated):
        p.write_bytes(b"x")
    assert acquire.member_paths(primary) == [primary, extra]


# ---------------------------------------------------------------------
# Coarse pairing and area weights
# ---------------------------------------------------------------------

COARSE_LATS = np.array([12.5, 12.25, 12.0, 11.75])
COARSE_LONS = np.array([76.75, 77.0, 77.25, 77.5])


def test_bilinear_weights_sum_to_one_and_use_enclosing_points():
    w = pairing.bilinear_weights(COARSE_LATS, COARSE_LONS, 12.1, 77.1)
    assert sum(x[2] for x in w) == pytest.approx(1.0)
    assert {(a, b) for a, b, _ in w} == {(12.0, 77.0), (12.0, 77.25), (12.25, 77.0), (12.25, 77.25)}
    assert all(x[2] >= 0 for x in w)


def test_bilinear_is_exact_at_a_grid_node():
    w = {(a, b): x for a, b, x in pairing.bilinear_weights(COARSE_LATS, COARSE_LONS, 12.0, 77.0)}
    assert w[(12.0, 77.0)] == pytest.approx(1.0)


def test_bilinear_reproduces_a_linear_field():
    field = lambda lat, lon: 3.0 * lat - 2.0 * lon + 1.0  # noqa: E731
    w = pairing.bilinear_weights(COARSE_LATS, COARSE_LONS, 12.1, 77.2)
    assert sum(x * field(a, b) for a, b, x in w) == pytest.approx(field(12.1, 77.2))


def test_bilinear_refuses_to_extrapolate():
    with pytest.raises(ValueError):
        pairing.bilinear_weights(COARSE_LATS, COARSE_LONS, 13.0, 77.0)


def test_nearest_coarse_point_for_yelandur_target_cells():
    assert pairing.nearest_coarse_point(COARSE_LATS, COARSE_LONS, 12.1, 77.0)[:2] == (12.0, 77.0)
    assert pairing.nearest_coarse_point(COARSE_LATS, COARSE_LONS, 12.1, 77.1)[:2] == (12.0, 77.0)
    assert pairing.nearest_coarse_point(COARSE_LATS, COARSE_LONS, 12.0, 77.2)[:2] == (12.0, 77.25)


def test_area_weights_sum_to_one_on_real_gp():
    from era5_linkage.era5_linkage_data import get_panchayat
    from spatial_proxy.spatial_proxy_data import load_layer

    link = get_panchayat("Yariyuru")
    proxy = next(g for g in load_layer()["panchayats"] if g["panchayat_name"] == "Yariyuru")
    lats = np.array([12.2, 12.1, 12.0, 11.9])
    lons = np.array([76.9, 77.0, 77.1, 77.2, 77.3])
    w = pairing.area_weights(proxy["geometry"], lats, lons, link["intersecting_cells"])
    assert sum(w.values()) == pytest.approx(1.0)
    assert len(w) == link["intersecting_cell_count"]
    assert max(w, key=w.get) == (link["nearest_grid_latitude"], link["nearest_grid_longitude"])


# ---------------------------------------------------------------------
# Leakage-safe splits
# ---------------------------------------------------------------------

def _toy_rows():
    ts = pd.Series(pd.to_datetime(
        ["2021-06-01T00:00Z", "2022-12-24T23:00Z", "2022-12-25T00:00Z", "2022-12-31T23:00Z",
         "2023-01-01T00:00Z", "2023-12-31T23:00Z"], utc=True))
    rows = []
    for group in ("A", "B"):
        for primary in (True, False):
            for t in ts:
                rows.append({"cell_group_id": group, "in_primary": primary, "ts": t, "missing": False})
    df = pd.DataFrame(rows)
    df.loc[0, "missing"] = True
    return df


def test_temporal_periods_and_embargo():
    df = _toy_rows()
    period = splits.temporal_period(df["ts"])
    assert period.iloc[:6].tolist() == ["train_period", "train_period", "embargo", "embargo", "test_period", "test_period"]
    assert splits.TEST_START - splits.EMBARGO_START == pd.Timedelta(days=7)


def test_temporal_period_rejects_out_of_window():
    with pytest.raises(ValueError):
        splits.temporal_period(pd.Series(pd.to_datetime(["2020-12-31T23:00Z"], utc=True)))


def test_fold_roles_are_leakage_safe():
    df = _toy_rows()
    period = splits.temporal_period(df["ts"])
    role = splits.fold_roles(df["cell_group_id"], df["in_primary"], period, df["missing"], "A")
    train, test = df[role == "train"], df[role == "test"]
    assert set(train["cell_group_id"]) == {"B"}
    assert set(test["cell_group_id"]) == {"A"}
    assert train["ts"].max() + pd.Timedelta(days=7) <= test["ts"].min()
    assert role[~df["in_primary"]].eq("excluded").all()
    assert role[df["missing"]].eq("excluded").all()
    assert role[period == "embargo"].eq("excluded").all()


def test_spatial_folds_deterministic():
    assert splits.spatial_folds(["b", "a", "b", "c"]) == ["a", "b", "c"]


def test_cell_group_id_format():
    assert cell_group_id(12.1, 77.19999999999999) == "E5L_12.10N_77.20E"


# ---------------------------------------------------------------------
# Manifest contract
# ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def manifest():
    if not MANIFEST_PATH.exists():
        pytest.skip("manifest not built")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_records_required_facts(manifest):
    assert manifest["spatial_groups"]["effective_spatial_sample_size"] == 4
    assert len(manifest["spatial_groups"]["cell_groups"]) == 4
    assert manifest["coverage"]["complete_gp_count"] == 10
    assert len(manifest["coverage"]["primary_evaluation_population"]) == 10
    assert "Agara" in manifest["coverage"]["partial"]
    assert "Mamballi" in manifest["coverage"]["unavailable"]
    assert "Mamballi" not in manifest["coverage"]["rows_by_gp"]
    assert manifest["source_note"] == SOURCE_NOTE
    assert manifest["coarse_input"]["is_forecast"] is False
    assert manifest["coarse_input"]["product_type"] == "reanalysis"
    assert manifest["target"]["product_type"] == "reanalysis"
    assert manifest["known_limitations"]
    assert len(manifest["split_methodology"]["folds"]) == 4


def test_manifest_folds_disjoint_in_space_and_time(manifest):
    for fold in manifest["split_methodology"]["folds"]:
        assert fold["held_out_cell_group"] not in fold["train_cell_groups"]
        train_end = pd.Timestamp(fold["train_time_range_utc"][1])
        test_start = pd.Timestamp(fold["test_time_range_utc"][0])
        assert train_end + pd.Timedelta(days=7) <= test_start
        assert "Agara" not in fold["test_gps"]


def test_manifest_has_no_forbidden_terminology(manifest):
    text = json.dumps(manifest, ensure_ascii=False).lower()
    for term in FORBIDDEN_TERMS:
        assert term not in text, term


def test_manifest_upstream_hashes_match_current_files(manifest):
    import hashlib

    from multi_gp.build import REPO_ROOT

    for key in ("spatial_proxy", "elevation", "era5_linkage"):
        entry = manifest["provenance"][key]
        assert hashlib.sha256((REPO_ROOT / entry["file"]).read_bytes()).hexdigest() == entry["sha256"], key


# ---------------------------------------------------------------------
# Dataset contract (gitignored Parquet; skipped where absent)
# ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def data():
    if not DATASET_PATH.exists():
        pytest.skip("Parquet dataset not present locally")
    return pd.read_parquet(DATASET_PATH)


def test_dataset_row_count_and_population(data, manifest):
    assert len(data) == manifest["row_count"]
    assert data["gp_name"].nunique() == 11
    assert "Mamballi" not in set(data["gp_name"])
    hours = data["timestamp_utc"].nunique()
    assert len(data) == 11 * hours * 5


def test_every_row_is_labelled_reanalysis_proxy(data):
    assert data["source_note"].eq(SOURCE_NOTE).all()
    assert data["target_definition"].nunique() == 1


def test_agara_flagged_and_never_in_a_fold(data):
    agara = data[data["gp_name"] == "Agara"]
    assert agara["coverage_status"].eq("PARTIAL").all()
    assert not agara["in_primary_population"].any()
    for k in range(1, 5):
        assert agara[f"split_fold_{k}"].eq("excluded").all()


def test_dataset_folds_leakage_safe(data):
    for k in range(1, 5):
        col = data[f"split_fold_{k}"]
        train, test = data[col == "train"], data[col == "test"]
        assert len(train) and len(test)
        assert not set(train["cell_group_id"]) & set(test["cell_group_id"])
        assert test["cell_group_id"].nunique() == 1
        assert train["timestamp_utc"].max() + pd.Timedelta(days=7) <= test["timestamp_utc"].min()
        assert train["target_value"].notna().all() and test["target_value"].notna().all()


def test_target_identical_within_cell_group(data):
    wide = data.pivot_table(index=["timestamp_utc", "variable"], columns="gp_name", values="target_value")
    groups = data.drop_duplicates("gp_name").set_index("gp_name")["cell_group_id"]
    for _, members in groups.groupby(groups):
        cols = wide[members.index.tolist()]
        assert (cols.nunique(axis=1, dropna=False) <= 1).all()


def test_target_cells_exist_in_linkage(data):
    from era5_linkage.era5_linkage_data import get_panchayat

    for name, row in data.drop_duplicates("gp_name").set_index("gp_name").iterrows():
        link = get_panchayat(name)
        assert row["target_cell_latitude"] == link["nearest_grid_latitude"]
        assert row["target_cell_longitude"] == link["nearest_grid_longitude"]


def test_only_first_step_rainfall_is_missing(data):
    missing = data[data["target_value"].isna()]
    assert missing["variable"].eq("rainfall_mm").all()
    assert missing["target_missing_reason"].eq("ERA5_LAND_DEACCUMULATION_FIRST_STEP").all()
    assert missing["timestamp_utc"].nunique() == 1
    assert data["coarse_bilinear_value"].notna().all()


def test_clamped_rainfall_steps_are_rounding_noise_only(manifest):
    # A real de-accumulation convention error would produce clamped steps of
    # whole millimetres; float32 rounding of an unchanged accumulation is ~1e-5 mm.
    assert manifest["rainfall_quality"]["max_abs_clamped_step_mm"] < 1e-3


def test_timestamps_utc_and_ist_date(data):
    assert str(data["timestamp_utc"].dt.tz) == "UTC"
    sample = data.iloc[[0, -1]]
    for _, row in sample.iterrows():
        assert row["local_date_ist"] == (row["timestamp_utc"] + pd.Timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")


def test_units_consistent_between_coarse_and_target(data):
    assert (data["coarse_unit"] == data["target_unit"]).all()
