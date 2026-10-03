"""
Feature variants for the Stage 3A ablation. Each variant is a strict
superset of the previous one, built from the Stage 2 feature groups, so C4
is Stage 2's Model C feature list in the identical column order.
"""

from ml_stage2.features import COARSE_FEATURES, FEATURES as STAGE2_FEATURES, TIME_FEATURES

ELEVATION_FEATURES = ["elevation_mean_m", "elevation_range_m"]
SPATIAL_FEATURES = ["centroid_to_cell_km", "intersecting_cell_count"]

VARIANTS = {
    "C1_coarse_weather": COARSE_FEATURES,
    "C2_plus_elevation": COARSE_FEATURES + ELEVATION_FEATURES,
    "C3_plus_spatial": COARSE_FEATURES + ELEVATION_FEATURES + SPATIAL_FEATURES,
    "C4_plus_time_full_C": COARSE_FEATURES + ELEVATION_FEATURES + SPATIAL_FEATURES + TIME_FEATURES,
}
VARIANT_NAMES = list(VARIANTS)

# (from, to, feature group added)
INCREMENTS = [
    ("C1_coarse_weather", "C2_plus_elevation", "elevation"),
    ("C2_plus_elevation", "C3_plus_spatial", "spatial_context"),
    ("C3_plus_spatial", "C4_plus_time_full_C", "temporal"),
    ("C1_coarse_weather", "C4_plus_time_full_C", "all_non_weather_groups"),
]

assert VARIANTS["C4_plus_time_full_C"] == STAGE2_FEATURES, "C4 must equal Stage 2 Model C features exactly"
