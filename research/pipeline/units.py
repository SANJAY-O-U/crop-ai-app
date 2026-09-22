"""
Unit conversions — every conversion here is a standard, documented formula.
Nothing here is fitted or guessed; this is the difference between this
module and backend/app/downscaling/baseline.py's placeholder coefficients.

ERA5-Land raw units (as delivered by the CDS API), and what we convert them
to for the rest of this pipeline:

    2m_temperature            Kelvin (K)         -> Celsius (C)
    2m_dewpoint_temperature   Kelvin (K)         -> Celsius (C)
    total_precipitation       metres, ACCUMULATED-> millimetres (mm), per-hour
    10m_u/v_component_of_wind metres/second      -> combined speed, km/h
    relative_humidity_pct     NOT a raw ERA5-Land variable — derived below

total_precipitation's accumulation convention (once-daily forecast base at
00 UTC — verified against a real pilot download AND ECMWF's documentation,
see deaccumulate_era5_land_precipitation_m()'s docstring for the exact
source quote) is the one actually used by this pipeline's real-file path;
deaccumulate_precipitation_m() is a simpler generic helper for an
already-single-cycle series and does not implement that convention.

Source for ERA5-Land's variable set and accumulation convention:
https://confluence.ecmwf.int/display/CKB/ERA5-Land:+data+documentation
"""

import math


def kelvin_to_celsius(kelvin: float) -> float:
    return kelvin - 273.15


def deaccumulate_precipitation_m(accumulated_m: list[float]) -> list[float]:
    """
    GENERIC single-cycle de-accumulation: given a series already known to
    span exactly one uninterrupted accumulation cycle (no cycle-boundary
    crossing), subtract each value from its predecessor.

    NOTE: this function's original docstring assumed ERA5-Land resets at
    both 00 AND 12 UTC. That assumption was WRONG — verified against a real
    downloaded pilot file and ECMWF's own documentation
    (https://confluence.ecmwf.int/display/CKB/ERA5-Land:+data+documentation):
    ERA5-Land forecasts are initialised ONCE daily at 00 UTC (steps 1-24);
    12 UTC is an ordinary mid-cycle step, not a reset. For real ERA5-Land
    series spanning multiple days, use
    deaccumulate_era5_land_precipitation_m() below instead — it implements
    the documented convention exactly, including the 00 UTC boundary. This
    function is kept as-is (unchanged behaviour, unchanged tests) since it
    is still valid for any already-single-cycle input.
    """
    if not accumulated_m:
        return []
    hourly = [accumulated_m[0]]
    for i in range(1, len(accumulated_m)):
        hourly.append(max(0.0, accumulated_m[i] - accumulated_m[i - 1]))
    return hourly


def deaccumulate_era5_land_precipitation_m(
    values: list[float | None], hours_utc: list[int]
) -> tuple[list[float | None], list[int]]:
    """
    De-accumulate real ERA5-Land total_precipitation using the DOCUMENTED
    convention (verified against a real pilot download AND ECMWF's own
    documentation, not guessed):

      https://confluence.ecmwf.int/display/CKB/ERA5-Land:+data+documentation
      "The data parameters are labelled as analyses and short (24 hour)
       forecasts initialised once daily from analyses at 00 UTC... the
       accumulations... are accumulated from the beginning of the forecast
       to the end of the forecast step... For the CDS time of 00 UTC, the
       accumulations are over the 24 hours ending at 00 UTC, so the data
       time-stamped YYYY/MM/DD 00:00 represents the total daily
       accumulation for the date YYYY/MM/DD-1."

    Concretely: ERA5-Land's forecast base time is 00 UTC, ONCE per day (NOT
    00 and 12 UTC as commonly assumed for plain ERA5). Step 1 (hour 01 UTC)
    is a fresh 1-hour accumulation. Steps 2-24 (hours 02-23, then hour 00 of
    the NEXT day = step 24) accumulate continuously from that same 00 UTC
    base — 12 UTC is an ordinary mid-cycle step with no special reset
    behaviour, and hour 00 of a day is numerically on the SAME cycle/scale
    as hour 23 of the day before it (they differ only in forecast step
    number, 23 vs 24), so a plain consecutive difference is correct there.

    Algorithm, per index i (chronological order, one entry per hourly step):
      - i == 0 (the first timestep of the whole input) AND hours_utc[0] != 1:
            no earlier data exists to de-accumulate against -> None (missing,
            never guessed). If hours_utc[0] == 1, it needs no earlier data at
            all (see next rule) and is NOT missing.
      - hours_utc[i] == 1 (a fresh cycle's first step): hourly value = the
            raw value itself, unchanged — the cycle restarts from 0 at each
            day's 00 UTC base, so step 1 already IS the true 1-hour amount.
            Never computed as raw[i] - raw[i-1], since raw[i-1] belongs to
            the PREVIOUS (closed) cycle and subtracting it would produce a
            large, meaningless negative number.
      - any other hour (02-23, or 00 continuing the previous day's cycle):
            hourly value = raw[i] - raw[i-1], both on the same cycle/scale.
      - a None/NaN input at index i, or a None predecessor needed for the
            plain-difference case, propagates as None (never silently
            treated as 0 or skipped).
      - a NEGATIVE result from a plain-difference step (not an expected
            hour==1 reset) is physically impossible for precipitation and is
            clamped to 0.0 — but that index is recorded in the returned
            anomaly list, never silently discarded.

    Returns (hourly_values_m, anomaly_indices) — hourly_values_m is the same
    length as `values`, still in metres (unit conversion to mm stays
    precipitation_m_to_mm()'s separate job).
    """
    import math as _math

    n = len(values)
    if n != len(hours_utc):
        raise ValueError("values and hours_utc must be the same length")
    if n == 0:
        return [], []

    hourly: list[float | None] = [None] * n
    anomalies: list[int] = []

    def _is_missing(x) -> bool:
        return x is None or (isinstance(x, float) and _math.isnan(x))

    for i in range(n):
        raw_i = values[i]

        if hours_utc[i] == 1:
            # Fresh cycle start — needs no predecessor at all.
            hourly[i] = None if _is_missing(raw_i) else float(raw_i)
            continue

        if i == 0:
            # First timestep of the whole window, and NOT a fresh-cycle
            # hour: we have no earlier data to subtract from, and cannot
            # tell how much of raw_i belongs to hours before our window.
            hourly[i] = None
            continue

        raw_prev = values[i - 1]
        if _is_missing(raw_i) or _is_missing(raw_prev):
            hourly[i] = None
            continue

        diff = float(raw_i) - float(raw_prev)
        if diff < 0:
            anomalies.append(i)
            diff = 0.0
        hourly[i] = diff

    return hourly, anomalies


def precipitation_m_to_mm(metres: float) -> float:
    return metres * 1000.0


def wind_components_to_speed_kmph(u_mps: float, v_mps: float) -> float:
    speed_mps = math.sqrt(u_mps ** 2 + v_mps ** 2)
    return speed_mps * 3.6


def relative_humidity_pct(temperature_c: float, dewpoint_c: float) -> float:
    """
    Magnus-Tetens approximation — standard meteorological formula, not a
    fitted/guessed coefficient. ERA5-Land has no direct relative-humidity
    variable, so this MUST be derived from 2m_temperature and
    2m_dewpoint_temperature.

    RH = 100 * e(Td) / e(T),  where e(x) = exp(17.625*x / (243.04+x))

    Reference: Alduchov & Eskridge (1996), "Improved Magnus Form
    Approximation of Saturation Vapor Pressure."
    """
    def _saturation_vapor_term(t_c: float) -> float:
        return math.exp((17.625 * t_c) / (243.04 + t_c))

    rh = 100.0 * _saturation_vapor_term(dewpoint_c) / _saturation_vapor_term(temperature_c)
    return max(0.0, min(100.0, rh))
