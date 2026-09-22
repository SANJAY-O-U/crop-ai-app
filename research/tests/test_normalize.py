import pandas as pd

from pipeline import units
from pipeline.coordinates import extract_point_timeseries
from pipeline.normalize import (
    ERA5_LAND_SHORT_NAME_TO_CANONICAL,
    RAW_VARIABLES,
    SOURCE_LABEL,
    normalize_era5_land_file,
    normalize_point_records,
)
from synthetic_fixtures import make_synthetic_era5_dataset, make_synthetic_era5_dataset_real_naming


def _extract_and_deaccumulate(ds, lat, lon):
    """The real intended two-step flow: extract raw records, then
    de-accumulate precipitation (a single-forecast-cycle assumption holds
    for this 3-hour synthetic fixture) before normalizing."""
    records = extract_point_timeseries(ds, lat, lon, RAW_VARIABLES)
    precip_raw = [r["total_precipitation"] for r in records]
    precip_hourly = units.deaccumulate_precipitation_m(precip_raw)
    for record, hourly_value in zip(records, precip_hourly):
        record["total_precipitation"] = hourly_value
    return records


def test_timestamp_normalization_produces_sorted_pandas_timestamps():
    ds = make_synthetic_era5_dataset()
    records = _extract_and_deaccumulate(ds, 13.4, 77.7)
    df = normalize_point_records(records, 13.4, 77.7)

    timestamps = df["timestamp"].drop_duplicates().sort_values().tolist()
    assert all(isinstance(t, pd.Timestamp) for t in timestamps)
    assert timestamps == sorted(timestamps)
    assert len(timestamps) == 3


def test_normalize_converts_temperature_and_labels_source():
    ds = make_synthetic_era5_dataset()
    records = _extract_and_deaccumulate(ds, 13.4, 77.7)
    df = normalize_point_records(records, 13.4, 77.7)

    temp_rows = df[df["variable"] == "temperature_c"]
    assert len(temp_rows) == 3
    assert round(temp_rows.iloc[0]["value"], 2) == round(units.kelvin_to_celsius(300.0), 2)
    assert (df["source"] == SOURCE_LABEL).all()
    assert (df["unit"] == df["variable"].map({
        "temperature_c": "C", "dewpoint_c": "C", "relative_humidity_pct": "%",
        "rainfall_mm": "mm", "wind_speed_kmph": "km/h",
    })).all()


def test_normalize_deaccumulated_rainfall_matches_expected_mm():
    ds = make_synthetic_era5_dataset()
    records = _extract_and_deaccumulate(ds, 13.4, 77.7)
    df = normalize_point_records(records, 13.4, 77.7)

    rainfall = df[df["variable"] == "rainfall_mm"].sort_values("timestamp")["value"].tolist()
    # Fixture accumulated precip was [0.001, 0.0025, 0.0025] m -> hourly [0.001, 0.0015, 0.0] m
    assert rainfall == [1.0, 1.5, 0.0]


def test_normalize_missing_dewpoint_skips_humidity_without_crashing():
    records = [{"time": "2023-06-01T00:00", "2m_temperature": 300.0}]  # no dewpoint at all
    df = normalize_point_records(records, 13.4, 77.7)

    assert "relative_humidity_pct" not in df["variable"].values
    assert "temperature_c" in df["variable"].values


def test_normalize_empty_records_returns_empty_dataframe_with_schema():
    df = normalize_point_records([], 13.4, 77.7)
    assert df.empty
    assert list(df.columns) == ["timestamp", "latitude", "longitude", "variable", "value", "unit", "source"]


# ── Real-file variable-name / coordinate-name mapping ─────────────────────────
# Real CDS ERA5-Land files use short names (t2m, d2m, tp, u10, v10) and a
# "valid_time" coordinate instead of "time" — see normalize.py's
# ERA5_LAND_SHORT_NAME_TO_CANONICAL and normalize_era5_land_file()'s docstring.

def test_short_name_mapping_covers_exactly_the_five_real_variables():
    assert ERA5_LAND_SHORT_NAME_TO_CANONICAL == {
        "t2m": "2m_temperature",
        "d2m": "2m_dewpoint_temperature",
        "tp": "total_precipitation",
        "u10": "10m_u_component_of_wind",
        "v10": "10m_v_component_of_wind",
    }


def test_normalize_era5_land_file_maps_real_short_names_and_valid_time(tmp_path):
    """
    End-to-end through normalize_era5_land_file(): a file shaped exactly
    like the real CDS response (short names, valid_time coordinate) must
    produce the SAME canonical output as the long-named/time-coordinate
    synthetic fixture with equivalent values.
    """
    real_shaped_ds = make_synthetic_era5_dataset_real_naming()
    nc_path = tmp_path / "real_shaped.nc"
    real_shaped_ds.to_netcdf(nc_path)

    df = normalize_era5_land_file(str(nc_path), 13.4, 77.7)

    # Canonical variable names appear in the output — never t2m/d2m/tp/u10/v10.
    produced_variables = set(df["variable"])
    assert produced_variables == {
        "temperature_c", "dewpoint_c", "relative_humidity_pct", "rainfall_mm", "wind_speed_kmph",
    }
    assert not (produced_variables & set(ERA5_LAND_SHORT_NAME_TO_CANONICAL))

    # Same numeric result as normalizing the long-named fixture directly
    # (proves the rename is purely a label change, not a value change).
    long_named_records = extract_point_timeseries(make_synthetic_era5_dataset(), 13.4, 77.7, RAW_VARIABLES)
    expected_df = normalize_point_records(long_named_records, 13.4, 77.7)

    actual_temp = df[df["variable"] == "temperature_c"].sort_values("timestamp")["value"].tolist()
    expected_temp = expected_df[expected_df["variable"] == "temperature_c"].sort_values("timestamp")["value"].tolist()
    assert actual_temp == expected_temp

    assert len(df["timestamp"].unique()) == 3


def test_normalize_era5_land_file_deaccumulates_rainfall_using_documented_convention(tmp_path):
    """
    Supersedes the old "rainfall is raw, not de-accumulated" behaviour: as
    of the Part A precipitation fix, normalize_era5_land_file() DOES
    de-accumulate, via the documented once-daily-00-UTC ERA5-Land
    convention. The fixture's timestamps are hours 00, 01, 02 of the same
    day, so: hour 00 (index 0) is the window's first timestep and NOT hour
    01 -> no rainfall_mm row at all for it (missing, never silently
    zeroed); hour 01 is a fresh-cycle hour -> raw value as-is; hour 02 is
    an ordinary within-cycle step -> plain difference against hour 01.
    """
    real_shaped_ds = make_synthetic_era5_dataset_real_naming()
    nc_path = tmp_path / "real_shaped.nc"
    real_shaped_ds.to_netcdf(nc_path)

    df = normalize_era5_land_file(str(nc_path), 13.4, 77.7)

    rainfall_rows = df[df["variable"] == "rainfall_mm"].sort_values("timestamp")
    # Fixture's raw (still-accumulated) precip_m was [0.001, 0.0025, 0.0025]
    # -> hour00: no row (first timestep, not hour 01)
    #    hour01: fresh cycle -> raw as-is -> 0.0025 m = 2.5 mm
    #    hour02: within-cycle diff -> (0.0025-0.0025) m = 0.0 mm
    assert len(rainfall_rows) == 2
    assert list(rainfall_rows["timestamp"].dt.hour) == [1, 2]
    assert rainfall_rows["value"].tolist() == [2.5, 0.0]
