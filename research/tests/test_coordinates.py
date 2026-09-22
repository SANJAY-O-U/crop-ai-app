from pipeline.coordinates import extract_point_timeseries, haversine_km, nearest_gridpoint
from synthetic_fixtures import make_synthetic_era5_dataset


def test_haversine_zero_distance_for_identical_points():
    assert haversine_km(13.4, 77.7, 13.4, 77.7) == 0.0


def test_haversine_known_short_distance():
    # ~0.1 degree of latitude is roughly 11 km
    d = haversine_km(13.4, 77.7, 13.5, 77.7)
    assert 10.0 < d < 12.5


def test_nearest_gridpoint_snaps_to_closest_cell():
    ds = make_synthetic_era5_dataset()
    # Grid has latitudes [13.5, 13.4] and longitudes [77.7, 77.8]
    point, distance_km = nearest_gridpoint(ds, latitude=13.42, longitude=77.72)
    assert float(point["latitude"].values) == 13.4
    assert float(point["longitude"].values) == 77.7
    assert distance_km >= 0


def test_extract_point_timeseries_returns_one_row_per_timestep():
    ds = make_synthetic_era5_dataset()
    rows = extract_point_timeseries(ds, 13.4, 77.7, ["2m_temperature", "total_precipitation"])
    assert len(rows) == 3  # fixture has 3 hourly timesteps
    for row in rows:
        assert "2m_temperature" in row
        assert "total_precipitation" in row
        assert "grid_distance_km" in row


def test_extract_point_timeseries_ignores_missing_variable_gracefully():
    ds = make_synthetic_era5_dataset()
    rows = extract_point_timeseries(ds, 13.4, 77.7, ["variable_that_does_not_exist"])
    assert len(rows) == 3
    assert "variable_that_does_not_exist" not in rows[0]
