"""
Spatial pairing for the Phase 2D multi-GP dataset. Pure functions only.

  - Coarse (ERA5 0.25 deg) -> each ERA5-Land 0.1 deg target cell center:
      * bilinear interpolation from the 4 enclosing ERA5 grid points
        (the primary coarse field -- see README.md for why), and
      * the single nearest ERA5 grid point (recorded for transparency;
        three of the four Yelandur target groups share the same nearest
        ERA5 point, so it alone cannot distinguish them).
    Both use ONLY coarse-grid values -- nothing from the ERA5-Land target.

  - Area weights of a GP's spatial-proxy geometry over the ERA5-Land cells
    it intersects (for the secondary area-weighted diagnostic). Cell
    polygons come from era5_linkage.linkage.build_cell_polygon -- the same
    cell construction the Phase 2C linkage used -- and areas are measured
    in EPSG:32643 (UTM 43N), the same projected CRS the spatial proxy uses
    for its own area math.
"""

import numpy as np

from era5_linkage import linkage
from pipeline.coordinates import haversine_km

AREA_CRS = "EPSG:32643"


def _bracket(values: np.ndarray, x: float) -> tuple[int, int, float]:
    """Indices (i0, i1) of the two grid values enclosing x and the fraction
    of the way from values[i0] to values[i1]. Works for ascending or
    descending axes. Raises if x is outside the axis -- no extrapolation."""
    values = np.asarray(values, dtype=float)
    lo, hi = float(values.min()), float(values.max())
    if not lo <= x <= hi:
        raise ValueError(f"{x} is outside the coarse grid axis [{lo}, {hi}]; refusing to extrapolate")
    order = np.argsort(values)
    sorted_vals = values[order]
    j = int(np.searchsorted(sorted_vals, x, side="right")) - 1
    j = min(max(j, 0), len(sorted_vals) - 2)
    a, b = sorted_vals[j], sorted_vals[j + 1]
    frac = 0.0 if b == a else (x - a) / (b - a)
    return int(order[j]), int(order[j + 1]), float(frac)


def bilinear_weights(coarse_lats, coarse_lons, lat: float, lon: float) -> list[tuple[float, float, float]]:
    """[(coarse_lat, coarse_lon, weight), ...] for the 4 enclosing points,
    weights summing to 1. Zero-weight corners are kept so every target cell
    always lists the same 4 enclosing points."""
    i0, i1, fy = _bracket(coarse_lats, lat)
    j0, j1, fx = _bracket(coarse_lons, lon)
    lats = np.asarray(coarse_lats, dtype=float)
    lons = np.asarray(coarse_lons, dtype=float)
    return [
        (float(lats[i0]), float(lons[j0]), (1 - fy) * (1 - fx)),
        (float(lats[i0]), float(lons[j1]), (1 - fy) * fx),
        (float(lats[i1]), float(lons[j0]), fy * (1 - fx)),
        (float(lats[i1]), float(lons[j1]), fy * fx),
    ]


def nearest_coarse_point(coarse_lats, coarse_lons, lat: float, lon: float) -> tuple[float, float, float]:
    """(coarse_lat, coarse_lon, haversine distance km) of the nearest coarse
    grid point. Ties broken deterministically by (lat, lon) order."""
    best = None
    for clat in np.asarray(coarse_lats, dtype=float):
        for clon in np.asarray(coarse_lons, dtype=float):
            d = haversine_km(lat, lon, float(clat), float(clon))
            key = (round(d, 9), float(clat), float(clon))
            if best is None or key < best[0]:
                best = (key, float(clat), float(clon), d)
    return best[1], best[2], best[3]


def area_weights(geometry: dict, lat_values, lon_values, cells: list[dict]) -> dict[tuple[float, float], float]:
    """{(cell_lat, cell_lon): fraction of the GP geometry's area inside that
    cell}, normalized to sum to 1 over the given (intersecting) cells.
    Raises if the cells cover less than 99.9% of the geometry -- that would
    mean the grid does not contain the GP, and weights would be invented."""
    import shapely.geometry as sgeom
    from pyproj import Transformer
    from shapely.ops import transform

    to_utm = Transformer.from_crs("EPSG:4326", AREA_CRS, always_xy=True).transform
    gp = transform(to_utm, sgeom.shape(geometry))
    lat_values = np.asarray(lat_values, dtype=float)
    lon_values = np.asarray(lon_values, dtype=float)

    raw = {}
    for cell in cells:
        i = int(np.flatnonzero(lat_values == cell["latitude"])[0])
        j = int(np.flatnonzero(lon_values == cell["longitude"])[0])
        poly = transform(to_utm, linkage.build_cell_polygon(lat_values, lon_values, i, j))
        raw[(cell["latitude"], cell["longitude"])] = gp.intersection(poly).area
    total = sum(raw.values())
    if total < 0.999 * gp.area:
        raise ValueError(f"intersecting cells cover only {total / gp.area:.4f} of the GP geometry")
    return {k: v / total for k, v in raw.items()}
