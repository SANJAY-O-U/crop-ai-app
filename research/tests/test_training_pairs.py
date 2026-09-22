import pandas as pd

from pipeline.training_pairs import TRAINING_PAIR_COLUMNS, build_training_pairs


def _long_df(timestamps, variable, values, source="era5_land_reanalysis_proxy"):
    return pd.DataFrame({
        "timestamp": timestamps, "latitude": 13.4, "longitude": 77.7,
        "variable": variable, "value": values, "unit": "C", "source": source,
    })


BLOCK = {"block_id": "BLOCK-DEMO-001", "latitude": 13.40, "longitude": 77.73, "elevation_m": 929.0}

PANCHAYATS = [
    {"panchayat_id": "PANCH-DEMO-001", "block_id": "BLOCK-DEMO-001",
     "latitude": 13.37, "longitude": 77.68, "elevation_m": 1393.0, "landcover_class": None},
    {"panchayat_id": "PANCH-DEMO-002", "block_id": "BLOCK-DEMO-001",
     "latitude": 13.47, "longitude": 77.50, "elevation_m": 741.0, "landcover_class": "cropland"},
]


def test_training_pair_schema_matches_expected_columns():
    ts = ["2023-06-01T00:00", "2023-06-01T01:00"]
    coarse = _long_df(ts, "temperature_c", [27.0, 27.5])
    fine = {
        "PANCH-DEMO-001": _long_df(ts, "temperature_c", [24.0, 24.5]),
        "PANCH-DEMO-002": _long_df(ts, "temperature_c", [28.0, 28.3]),
    }

    pairs = build_training_pairs(coarse, fine, PANCHAYATS, BLOCK)
    assert list(pairs.columns) == TRAINING_PAIR_COLUMNS
    assert len(pairs) == 4  # 2 panchayats x 2 timestamps


def test_elevation_delta_computed_correctly():
    ts = ["2023-06-01T00:00"]
    coarse = _long_df(ts, "temperature_c", [27.0])
    fine = {"PANCH-DEMO-001": _long_df(ts, "temperature_c", [24.0])}

    pairs = build_training_pairs(coarse, fine, [PANCHAYATS[0]], BLOCK)
    assert pairs.iloc[0]["elevation_delta_m"] == 1393.0 - 929.0


def test_source_note_is_never_labeled_as_observation():
    ts = ["2023-06-01T00:00"]
    coarse = _long_df(ts, "temperature_c", [27.0])
    fine = {"PANCH-DEMO-001": _long_df(ts, "temperature_c", [24.0])}

    pairs = build_training_pairs(coarse, fine, [PANCHAYATS[0]], BLOCK)
    assert pairs.iloc[0]["source_note"] == "reanalysis proxy — not observation"
    assert "observation" not in pairs.iloc[0]["source_note"].replace("not observation", "")


def test_panchayat_with_no_fine_data_is_skipped_not_crashed():
    ts = ["2023-06-01T00:00"]
    coarse = _long_df(ts, "temperature_c", [27.0])
    fine = {"PANCH-DEMO-001": _long_df(ts, "temperature_c", [24.0])}  # PANCH-DEMO-002 missing entirely

    pairs = build_training_pairs(coarse, fine, PANCHAYATS, BLOCK)
    assert set(pairs["panchayat_id"]) == {"PANCH-DEMO-001"}


def test_empty_coarse_data_returns_empty_schema_not_crash():
    empty_coarse = pd.DataFrame(columns=["timestamp", "latitude", "longitude", "variable", "value", "unit", "source"])
    pairs = build_training_pairs(empty_coarse, {}, PANCHAYATS, BLOCK)
    assert pairs.empty
    assert list(pairs.columns) == TRAINING_PAIR_COLUMNS


def test_non_overlapping_timestamps_produce_no_pairs():
    coarse = _long_df(["2023-06-01T00:00"], "temperature_c", [27.0])
    fine = {"PANCH-DEMO-001": _long_df(["2023-06-01T05:00"], "temperature_c", [24.0])}  # disjoint time

    pairs = build_training_pairs(coarse, fine, [PANCHAYATS[0]], BLOCK)
    assert pairs.empty
