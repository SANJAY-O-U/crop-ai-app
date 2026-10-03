"""
Pure spatial-linkage functions between an ERA5-Land grid (as an xarray
Dataset with "latitude"/"longitude" coordinates -- the same shape real
CDS-delivered files and research/synthetic_fixtures.py's fixture both use)
and a Panchayat spatial-proxy geometry/centroid.

REUSES existing infrastructure rather than re-implementing it:
  - pipeline.coordinates.nearest_gridpoint / haversine_km for the centroid
    link (the SAME nearest-gridpoint + haversine code path already used by
    the Phase 2A/2B normalization pipeline -- no second implementation).

GRID INTERPRETATION (documented once, here, since every function in this
module depends on it): ERA5-Land grid coordinates are CELL CENTERS, not
polygon corners. A grid latitude/longitude value names the middle of a
~0.1-degree cell, not an edge. Cell polygons must therefore be DERIVED from
the midpoints between neighboring centers -- never read directly off the
coordinate values themselves. See build_cell_polygon()'s docstring for the
exact edge-construction rule, including the documented outermost-cell case.
"""

import numpy as np
import shapely.geometry as sgeom

from pipeline.coordinates import haversine_km, nearest_gridpoint


def infer_axis_order(values: np.ndarray) -> str:
    """"ascending" or "descending", based on the actual array order -- never
    assumed. Real ERA5-Land files store latitude descending (north to
    south) and longitude ascending (west to east), confirmed this session
    against data/raw/era5_land/era5_land_pilot_202306.nc, but this function
    reads the order from whatever array it's given rather than hardcoding
    that expectation."""
    if len(values) < 2:
        raise ValueError("cannot determine axis order from fewer than 2 points")
    return "descending" if values[0] > values[-1] else "ascending"


def infer_grid_spacing_deg(values: np.ndarray, tolerance: float = 1e-6) -> float:
    """Absolute spacing between consecutive grid points, read from the
    actual coordinate array. Raises if the spacing is not uniform -- this
    module never silently assumes a regular grid without checking."""
    if len(values) < 2:
        raise ValueError("cannot infer spacing from fewer than 2 points")
    diffs = np.abs(np.diff(np.asarray(values, dtype=float)))
    if not np.allclose(diffs, diffs[0], atol=tolerance):
        raise ValueError(f"grid spacing is not uniform: {diffs}")
    return float(diffs[0])


def describe_grid(lat_values: np.ndarray, lon_values: np.ndarray) -> dict:
    """A compact, evidence-based description of a real grid's convention --
    used both for documentation (grid_metadata in the output) and as an
    explicit, testable statement of the ordering/spacing this module
    assumes nothing about ahead of time."""
    return {
        "latitude_order": infer_axis_order(lat_values),
        "longitude_order": infer_axis_order(lon_values),
        "latitude_spacing_deg": infer_grid_spacing_deg(lat_values),
        "longitude_spacing_deg": infer_grid_spacing_deg(lon_values),
        "n_latitude": int(len(lat_values)),
        "n_longitude": int(len(lon_values)),
        "latitude_min": float(np.min(lat_values)),
        "latitude_max": float(np.max(lat_values)),
        "longitude_min": float(np.min(lon_values)),
        "longitude_max": float(np.max(lon_values)),
    }


def nearest_grid_cell(dataset, latitude: float, longitude: float) -> dict:
    """Centroid link (Part A). Wraps pipeline.coordinates.nearest_gridpoint
    (the existing, already-tested nearest-cell + haversine-distance code)
    rather than re-implementing nearest-neighbor search. The returned
    nearest lat/lon are guaranteed by xarray's own .sel(method="nearest")
    to be values that actually exist in `dataset`'s coordinate arrays."""
    point, distance_km = nearest_gridpoint(dataset, latitude, longitude)
    nearest_lat = float(point["latitude"].values)
    nearest_lon = float(point["longitude"].values)
    return {
        "nearest_grid_latitude": nearest_lat,
        "nearest_grid_longitude": nearest_lon,
        "latitude_difference_deg": latitude - nearest_lat,
        "longitude_difference_deg": longitude - nearest_lon,
        "centroid_to_grid_distance_km": distance_km,
    }


def _cell_edges_1d(values: np.ndarray, idx: int) -> tuple[float, float]:
    """The (low, high) edge of grid cell `idx` along one axis, derived from
    neighboring cell CENTERS (never read directly off `values[idx]` itself,
    which is a center, not an edge).

    Interior points (0 < idx < n-1): each edge is the midpoint to that
    side's immediate neighbor -- standard Voronoi/Thiessen construction for
    a 1D regular grid.

    Outermost points (idx == 0 or idx == n-1): only one neighbor exists, so
    only one edge can be derived from real data (the midpoint to that one
    neighbor). The OTHER edge -- which would require a neighbor beyond the
    grid's actual extent -- is constructed by mirroring that same
    real, data-derived half-width outward from the center, i.e. the
    outermost cell is given the SAME width as its one real interior
    neighbor pair. This is an explicit, documented choice, not a silent
    assumption: it is the standard "half-cell extrapolation" convention,
    and no coordinate value is ever shifted to make it work.
    """
    n = len(values)
    if n < 2:
        raise ValueError("cannot construct cell edges from a single-point axis")

    v = float(values[idx])
    if idx == 0:
        neighbor_mid = (v + float(values[1])) / 2.0
        half_width = abs(neighbor_mid - v)
        far_edge = v - half_width if neighbor_mid > v else v + half_width
        edges = (neighbor_mid, far_edge)
    elif idx == n - 1:
        neighbor_mid = (v + float(values[idx - 1])) / 2.0
        half_width = abs(neighbor_mid - v)
        far_edge = v - half_width if neighbor_mid > v else v + half_width
        edges = (neighbor_mid, far_edge)
    else:
        edge_a = (v + float(values[idx - 1])) / 2.0
        edge_b = (v + float(values[idx + 1])) / 2.0
        edges = (edge_a, edge_b)

    return (min(edges), max(edges))


def build_cell_polygon(lat_values: np.ndarray, lon_values: np.ndarray, lat_idx: int, lon_idx: int) -> sgeom.Polygon:
    """The rectangular cell polygon for grid point (lat_idx, lon_idx),
    constructed per _cell_edges_1d's documented rule. Deterministic: the
    same (lat_values, lon_values, lat_idx, lon_idx) always produces the
    same polygon."""
    lat_low, lat_high = _cell_edges_1d(lat_values, lat_idx)
    lon_low, lon_high = _cell_edges_1d(lon_values, lon_idx)
    return sgeom.box(lon_low, lat_low, lon_high, lat_high)


def cells_intersecting_geometry(geometry: dict, lat_values: np.ndarray, lon_values: np.ndarray) -> list[dict]:
    """Part B: every grid cell whose derived polygon intersects the given
    GeoJSON-like geometry. Returns [] if the geometry lies entirely outside
    the grid's cells -- never fabricates a "nearest anyway" result here
    (that's nearest_grid_cell's job, a separate, explicit calculation)."""
    geom = sgeom.shape(geometry)
    geom_minx, geom_miny, geom_maxx, geom_maxy = geom.bounds

    hits = []
    for i, lat in enumerate(lat_values):
        lat_low, lat_high = _cell_edges_1d(lat_values, i)
        if lat_high < geom_miny or lat_low > geom_maxy:
            continue
        for j, lon in enumerate(lon_values):
            lon_low, lon_high = _cell_edges_1d(lon_values, j)
            if lon_high < geom_minx or lon_low > geom_maxx:
                continue
            cell_poly = sgeom.box(lon_low, lat_low, lon_high, lat_high)
            if cell_poly.intersects(geom):
                hits.append({"latitude": float(lat), "longitude": float(lon)})
    return hits


__all__ = [
    "infer_axis_order",
    "infer_grid_spacing_deg",
    "describe_grid",
    "nearest_grid_cell",
    "build_cell_polygon",
    "cells_intersecting_geometry",
    "haversine_km",
]
