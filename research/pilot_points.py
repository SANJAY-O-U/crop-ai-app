"""
Research pilot points — deliberately SEPARATE from
backend/app/geospatial/seed_data.py (which defines the LIVE CropCast demo
API's block/panchayats). This file is the research pipeline's own copy, so
research-only fixes (like the grid-cell-collision fix below) never touch
the live API. Per Phase 2A.1's explicit scope limit ("keep all work under
research/"), this module is now what research/scripts/run_normalize.py
reads from instead of importing the backend package.

Every point below is explicitly demo/research data — NOT an official
administrative boundary or verified government coordinate. See
backend/app/geospatial/seed_data.py's own docstring for the same disclosure
in more detail (identical spirit, independent copy).

=== Phase 2A.1 grid-cell fix ===
The ERA5-Land pilot grid (from research/era5_land/acquire.py's PILOT_AREA)
has ~0.1 degree spacing: latitude in {13.3, 13.4, 13.5}, longitude in
{77.5, 77.6, 77.7, 77.8, 77.9}. The ORIGINAL block centroid (13.40, 77.73)
and PANCH-DEMO-001 (13.370, 77.680) both snapped to the SAME nearest grid
cell (13.4, 77.7) — verified directly against the real downloaded file —
which made a block-vs-Panchayat-A comparison meaningless (identical
underlying data).

Fix applied: nudge ONLY the block's longitude, 77.73 -> 77.76 (about 3 km),
which snaps it to grid cell (13.4, 77.8) instead — distinct from all three
panchayats' cells. This was chosen over moving Panchayat A, because
Panchayat A's coordinates were originally chosen specifically to sit on a
real, large elevation feature (the Nandi Hills escarpment, ~1393m) that
does not recur at any nearby-but-distinct grid cell in this mostly-flat
plateau (checked: nearby candidate points all measured 900-960m — no
comparable contrast, confirmed by live Open-Meteo elevation lookups on
2026-09-22). Moving the block instead is the smaller, less lossy change,
and it remains well within the ALREADY-REQUESTED/ALREADY-DOWNLOADED
PILOT_AREA bounding box (no new CDS request needed).

The block's elevation_m (934.0) is a fresh, real Open-Meteo elevation
lookup for the NEW coordinates (13.40, 77.76) — not reused from the old
point's value (929.0 was for 13.40, 77.73).
"""

RESEARCH_BLOCK = {
    "block_id": "BLOCK-DEMO-001",
    "block_name": "Demo Block",
    "latitude": 13.40,
    "longitude": 77.76,  # nudged from 77.73 (Phase 2A.1 grid-cell fix, see module docstring)
    "elevation_m": 934.0,  # live Open-Meteo elevation lookup at the NEW coordinates, 2026-09-22
    "is_demo_data": True,
}

RESEARCH_PANCHAYATS = [
    {
        "panchayat_id": "PANCH-DEMO-001", "block_id": "BLOCK-DEMO-001", "panchayat_name": "Panchayat A",
        "latitude": 13.370, "longitude": 77.680, "elevation_m": 1393.0, "is_demo_data": True,
    },
    {
        "panchayat_id": "PANCH-DEMO-002", "block_id": "BLOCK-DEMO-001", "panchayat_name": "Panchayat B",
        "latitude": 13.470, "longitude": 77.500, "elevation_m": 741.0, "is_demo_data": True,
    },
    {
        "panchayat_id": "PANCH-DEMO-003", "block_id": "BLOCK-DEMO-001", "panchayat_name": "Panchayat C",
        "latitude": 13.500, "longitude": 77.900, "elevation_m": 850.0, "is_demo_data": True,
    },
]
