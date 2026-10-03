"""
ERA5-Land (0.1 deg) and ERA5 (0.25 deg) grid arithmetic for the offline
feasibility audit.

Both products are global regular lat/lon grids whose cell CENTRES lie on
integer multiples of the spacing. That convention is not assumed: it was
observed in every real file acquired for this project (ERA5-Land centres
11.9..12.2 N / 76.9..77.3 E for Yelandur and 13.3..13.5 N / 77.5..77.9 E for
the pilot; ERA5 centres 11.75..12.5 N / 76.75..77.5 E), and
test_stage4_spatial_generalization.py re-checks the functions below against
those real coordinate arrays.
"""

import math

ERA5_LAND_SPACING = 0.1
ERA5_SPACING = 0.25


def _nearest_centre(value: float, spacing: float) -> float:
    # floor(x + 0.5) rather than round() so exact half-way points break
    # consistently upward (Python's round() is banker's rounding).
    return round(math.floor(value / spacing + 0.5) * spacing, 6)


def era5_land_cell(lat: float, lon: float) -> tuple[float, float]:
    return _nearest_centre(lat, ERA5_LAND_SPACING), _nearest_centre(lon, ERA5_LAND_SPACING)


def era5_cell(lat: float, lon: float) -> tuple[float, float]:
    return _nearest_centre(lat, ERA5_SPACING), _nearest_centre(lon, ERA5_SPACING)


def cell_id(cell: tuple[float, float]) -> str:
    return f"E5L_{cell[0]:.2f}N_{cell[1]:.2f}E"


def parse_cell_id(cid: str) -> tuple[float, float]:
    """Inverse of cell_id: 'E5L_12.00N_77.10E' -> (12.0, 77.1)."""
    _, lat, lon = cid.split("_")
    return float(lat.rstrip("N")), float(lon.rstrip("E"))


def chebyshev_cells(a: tuple[float, float], b: tuple[float, float], spacing: float = ERA5_LAND_SPACING) -> int:
    return int(round(max(abs(a[0] - b[0]), abs(a[1] - b[1])) / spacing))


def enclosing_era5_box(cell: tuple[float, float]) -> tuple[float, float]:
    """South-west corner of the 0.25 deg ERA5 box whose 4 corners enclose an
    ERA5-Land cell centre (the Phase 2D bilinear pairing)."""
    return (round(math.floor(cell[0] / ERA5_SPACING + 1e-9) * ERA5_SPACING, 6),
            round(math.floor(cell[1] / ERA5_SPACING + 1e-9) * ERA5_SPACING, 6))
