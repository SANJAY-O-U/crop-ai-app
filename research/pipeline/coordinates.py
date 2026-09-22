"""
Nearest-gridpoint extraction from an ERA5-Land (or similar regular-grid)
xarray Dataset, plus the haversine distance to that gridpoint so callers
know exactly how far the "nearest" match actually is (ERA5-Land's native
grid is ~0.1 degrees, roughly 9-11 km — never silently pretend the grid
cell IS the point).
"""

import math

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def nearest_gridpoint(dataset, latitude: float, longitude: float):
    """
    Select the nearest grid cell to (latitude, longitude) in an xarray
    Dataset that has 'latitude'/'longitude' coordinates.
    Returns (selected_dataset_at_point, distance_km_to_that_gridpoint).
    """
    point = dataset.sel(latitude=latitude, longitude=longitude, method="nearest")
    actual_lat = float(point["latitude"].values)
    actual_lon = float(point["longitude"].values)
    distance_km = haversine_km(latitude, longitude, actual_lat, actual_lon)
    return point, distance_km


def extract_point_timeseries(dataset, latitude: float, longitude: float, variables: list[str]):
    """
    Extract a plain-Python time series for one point: a list of dicts, one
    per timestep, each with 'time' plus the requested variables' raw values
    (still in ERA5-Land's native units — unit conversion is units.py's job,
    not this function's).
    """
    point, distance_km = nearest_gridpoint(dataset, latitude, longitude)
    times = point["time"].values
    rows = []
    for i, t in enumerate(times):
        row = {"time": t, "grid_distance_km": distance_km}
        for var in variables:
            if var in point:
                values = point[var].values
                row[var] = float(values[i]) if values.ndim else float(values)
        rows.append(row)
    return rows
