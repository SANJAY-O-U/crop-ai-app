"""
Baseline downscaling method — Phase 1.

This is a transparent, elevation-aware adjustment applied to a single
block-level forecast to produce a per-panchayat estimate. It is NOT machine
learning and does not claim to be. Every value it produces says so via the
"method": "baseline" field on the response.

Two different kinds of constants are used below, and they are NOT of equal
scientific standing — read the comments on each:

  1. TEMPERATURE_LAPSE_RATE_C_PER_M (0.0065 C/m) is the International
     Standard Atmosphere environmental lapse rate — an established physical
     constant (temperature drops ~6.5C per 1000m of elevation gain). This is
     real physics, not a guess.

  2. The rainfall/humidity/wind factors below are ILLUSTRATIVE PLACEHOLDER
     HEURISTICS, not calibrated coefficients. Elevation genuinely does
     correlate with orographic rainfall, humidity and wind exposure in
     reality, but the *magnitude* of that effect is highly region-specific
     and cannot be honestly claimed without calibrating against real
     historical observations for this specific block. Phase 2's ML
     correction (see app/downscaling — not yet implemented) is exactly the
     piece that replaces these placeholders with values learned from data.
     Until then, they exist so panchayats are visibly differentiated from
     the block value in a physically plausible *direction*, and every
     response carries the exact coefficients used so this is auditable,
     not hidden.
"""

from app.weather.schemas import DailyWeather, PointForecast

TEMPERATURE_LAPSE_RATE_C_PER_M = 0.0065

# --- Placeholder heuristics below (see module docstring, point 2) ---
RAINFALL_OROGRAPHIC_FACTOR_PER_100M = 0.03    # +3% rainfall per 100m elevation gain
HUMIDITY_ADJUSTMENT_PCT_PER_100M = -0.5       # -0.5 percentage points per 100m elevation gain
WIND_FACTOR_PER_100M = 0.02                   # +2% wind speed per 100m elevation gain

_RAINFALL_FACTOR_BOUNDS = (0.5, 1.6)  # clamp so large elevation deltas can't produce absurd multipliers


def build_adjustment_metadata(block_elevation_m: float | None, panchayat_elevation_m: float | None) -> dict:
    if block_elevation_m is None or panchayat_elevation_m is None:
        return {
            "block_elevation_m": block_elevation_m,
            "panchayat_elevation_m": panchayat_elevation_m,
            "elevation_delta_m": None,
            "note": "Elevation unavailable for one or both points — baseline returned the block value unmodified.",
        }
    delta = panchayat_elevation_m - block_elevation_m
    return {
        "block_elevation_m": block_elevation_m,
        "panchayat_elevation_m": panchayat_elevation_m,
        "elevation_delta_m": round(delta, 1),
        "temperature_lapse_rate_c_per_m": TEMPERATURE_LAPSE_RATE_C_PER_M,
        "rainfall_orographic_factor_per_100m": RAINFALL_OROGRAPHIC_FACTOR_PER_100M,
        "humidity_adjustment_pct_per_100m": HUMIDITY_ADJUSTMENT_PCT_PER_100M,
        "wind_factor_per_100m": WIND_FACTOR_PER_100M,
        "coefficients_calibrated": False,
    }


def apply_baseline(
    block_forecast: PointForecast,
    block_elevation_m: float | None,
    panchayat_elevation_m: float | None,
) -> list[DailyWeather]:
    """Apply the elevation-aware adjustment to every day of a block forecast."""
    if block_elevation_m is None or panchayat_elevation_m is None:
        # No terrain data to work with — return the block's values unchanged
        # rather than fabricating an adjustment.
        return list(block_forecast.daily)

    delta_m = panchayat_elevation_m - block_elevation_m
    temp_shift_c = -TEMPERATURE_LAPSE_RATE_C_PER_M * delta_m

    rainfall_factor = 1 + RAINFALL_OROGRAPHIC_FACTOR_PER_100M * (delta_m / 100)
    rainfall_factor = max(_RAINFALL_FACTOR_BOUNDS[0], min(_RAINFALL_FACTOR_BOUNDS[1], rainfall_factor))

    humidity_shift_pct = HUMIDITY_ADJUSTMENT_PCT_PER_100M * (delta_m / 100)
    wind_factor = 1 + WIND_FACTOR_PER_100M * (delta_m / 100)

    adjusted = []
    for day in block_forecast.daily:
        adjusted.append(DailyWeather(
            date=day.date,
            temperature_min_c=round(day.temperature_min_c + temp_shift_c, 1),
            temperature_max_c=round(day.temperature_max_c + temp_shift_c, 1),
            rainfall_mm=round(max(0.0, day.rainfall_mm * rainfall_factor), 1),
            humidity_pct=round(min(100.0, max(0.0, day.humidity_pct + humidity_shift_pct)), 1),
            wind_kmph=round(max(0.0, day.wind_kmph * wind_factor), 1),
        ))
    return adjusted
