"""
================================================================================
 DEMO / SEED DATA — NOT OFFICIAL GOVERNMENT RECORDS
================================================================================
This is placeholder pilot data for exactly ONE block and THREE panchayats,
used to demonstrate the block -> panchayat downscaling pipeline end to end.

What is real here:
  - latitude/longitude: real, resolvable Earth coordinates spanning the
    plateau/escarpment terrain near Nandi Hills, Karnataka, India — chosen
    deliberately because this small area has genuinely large elevation
    contrast (roughly 740m to 1390m) within a plausible single-block
    radius, which is what makes elevation-aware downscaling visible in the
    demo instead of a rounding-error-sized difference. Naming this region is
    a statement about real terrain only — it is NOT a claim that any real,
    named Panchayat sits at these exact points. They are NOT verified
    official Panchayat boundary centroids from a survey/LGD dataset.
  - elevation_m: real DEM-derived values, fetched live from the Open-Meteo
    Elevation API (https://api.open-meteo.com/v1/elevation) for these exact
    coordinates during development. They are genuine terrain data, just not
    tied to a verified official panchayat boundary.

What is NOT real here:
  - block_id / panchayat_id: fabricated identifiers in an obviously
    non-official format (e.g. "BLOCK-DEMO-001"). These are NOT LGD codes or
    any other government identifier and must never be presented as such.
  - block_name / panchayat_name / district / state: generic placeholder
    names ("Demo Block", "Panchayat A/B/C"), chosen deliberately so nobody
    mistakes this for a real administrative unit.

Replace this entire file with real LGD-sourced boundary/centroid data before
any production or non-demo use. Every record carries is_demo_data=True so
downstream code (and API responses) can always tell.
================================================================================
"""

from app.geospatial.schemas import Block, Panchayat

DEMO_BLOCK = Block(
    block_id="BLOCK-DEMO-001",
    block_name="Demo Block",
    district="Demo District",
    state="Demo State (Karnataka region, approx.)",
    latitude=13.40,
    longitude=77.73,
    elevation_m=929.0,   # live Open-Meteo elevation lookup, see module docstring
    is_demo_data=True,
)

DEMO_PANCHAYATS = [
    Panchayat(
        # Escarpment point near Nandi Hills — genuinely ~464m higher than the
        # block centroid, so the temperature lapse-rate effect is clearly
        # visible (real physics), not lost in rounding.
        panchayat_id="PANCH-DEMO-001",
        panchayat_name="Panchayat A",
        block_id=DEMO_BLOCK.block_id,
        block_name=DEMO_BLOCK.block_name,
        district=DEMO_BLOCK.district,
        state=DEMO_BLOCK.state,
        latitude=13.370,
        longitude=77.680,
        elevation_m=1393.0,
        is_demo_data=True,
    ),
    Panchayat(
        # Lower plateau point — genuinely ~188m below the block centroid.
        panchayat_id="PANCH-DEMO-002",
        panchayat_name="Panchayat B",
        block_id=DEMO_BLOCK.block_id,
        block_name=DEMO_BLOCK.block_name,
        district=DEMO_BLOCK.district,
        state=DEMO_BLOCK.state,
        latitude=13.470,
        longitude=77.500,
        elevation_m=741.0,
        is_demo_data=True,
    ),
    Panchayat(
        # Near-block-average elevation — included deliberately so the demo
        # also shows a panchayat that DOESN'T differ much, which is the
        # honest outcome when local terrain is close to the block's.
        panchayat_id="PANCH-DEMO-003",
        panchayat_name="Panchayat C",
        block_id=DEMO_BLOCK.block_id,
        block_name=DEMO_BLOCK.block_name,
        district=DEMO_BLOCK.district,
        state=DEMO_BLOCK.state,
        latitude=13.500,
        longitude=77.900,
        elevation_m=850.0,
        is_demo_data=True,
    ),
]
