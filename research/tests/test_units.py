import math

from pipeline.units import (
    deaccumulate_era5_land_precipitation_m,
    deaccumulate_precipitation_m,
    kelvin_to_celsius,
    precipitation_m_to_mm,
    relative_humidity_pct,
    wind_components_to_speed_kmph,
)


def test_kelvin_to_celsius_freezing_point():
    assert kelvin_to_celsius(273.15) == 0.0


def test_kelvin_to_celsius_known_value():
    assert round(kelvin_to_celsius(300.0), 2) == 26.85


def test_precipitation_m_to_mm():
    assert precipitation_m_to_mm(0.0025) == 2.5


def test_deaccumulate_precipitation_first_hour_unchanged():
    hourly = deaccumulate_precipitation_m([0.001, 0.0025, 0.0025])
    assert hourly[0] == 0.001


def test_deaccumulate_precipitation_differences():
    hourly = deaccumulate_precipitation_m([0.001, 0.0025, 0.0025])
    assert round(hourly[1], 6) == 0.0015
    assert round(hourly[2], 6) == 0.0


def test_deaccumulate_precipitation_never_negative():
    # A tiny numerical-noise decrease should clamp to 0, not go negative
    hourly = deaccumulate_precipitation_m([0.002, 0.0019999])
    assert hourly[1] == 0.0


def test_deaccumulate_precipitation_empty_input():
    assert deaccumulate_precipitation_m([]) == []


def test_wind_components_to_speed_kmph_known_value():
    # 3-4-5 triangle: sqrt(3^2+4^2) = 5 m/s = 18 km/h
    speed = wind_components_to_speed_kmph(3.0, 4.0)
    assert math.isclose(speed, 18.0, rel_tol=1e-9)


def test_relative_humidity_equal_temp_and_dewpoint_is_100pct():
    # Saturated air: dewpoint == temperature -> RH should be ~100%
    rh = relative_humidity_pct(temperature_c=25.0, dewpoint_c=25.0)
    assert math.isclose(rh, 100.0, abs_tol=0.01)


def test_relative_humidity_lower_dewpoint_gives_lower_rh():
    rh = relative_humidity_pct(temperature_c=25.0, dewpoint_c=15.0)
    assert 0 < rh < 100


def test_relative_humidity_clamped_to_valid_range():
    # Dewpoint above temperature is physically unusual but must not blow past 100%
    rh = relative_humidity_pct(temperature_c=20.0, dewpoint_c=30.0)
    assert rh <= 100.0


# ── deaccumulate_era5_land_precipitation_m — documented ERA5-Land convention ──
# (once-daily 00 UTC forecast base; hour==1 is a fresh cycle; 12 UTC is an
# ORDINARY mid-cycle step, not a reset; hour==0 continues the previous cycle.
# See units.py's docstring for the ECMWF source.)

def test_ordinary_consecutive_accumulated_values_within_one_cycle():
    # hours 1,2,3: hour1 is fresh-cycle (raw as-is), 2 and 3 are plain diffs
    hourly, anomalies = deaccumulate_era5_land_precipitation_m(
        values=[0.001, 0.0025, 0.0040], hours_utc=[1, 2, 3],
    )
    assert hourly == [0.001, 0.0015, 0.0015]
    assert anomalies == []


def test_00_utc_boundary_continues_previous_cycle_not_a_reset():
    # hour 0 (index 2) must be a PLAIN DIFFERENCE against hour 23's value,
    # not treated as a reset -> confirms the "00 UTC continues, doesn't reset" fix.
    hourly, anomalies = deaccumulate_era5_land_precipitation_m(
        values=[0.008, 0.010, 0.0105, 0.0002], hours_utc=[22, 23, 0, 1],
    )
    assert hourly[2] == 0.0105 - 0.010
    assert anomalies == []


def test_12_utc_is_an_ordinary_mid_cycle_step_not_a_reset():
    # hour 12 (index 1) must ALSO be a plain difference — confirms the
    # (previously assumed, now disproven) "resets at 00 AND 12" idea is gone.
    hourly, anomalies = deaccumulate_era5_land_precipitation_m(
        values=[0.0030, 0.0035, 0.0040], hours_utc=[11, 12, 13],
    )
    assert hourly[1] == 0.0035 - 0.0030
    assert hourly[2] == 0.0040 - 0.0035
    assert anomalies == []


def test_fresh_cycle_hour_uses_raw_value_not_a_diff_against_previous_cycle():
    # hour 1 (index 3) must NOT be raw[3]-raw[2] (which would be a large,
    # meaningless negative number) — it must be the raw value itself.
    hourly, _ = deaccumulate_era5_land_precipitation_m(
        values=[0.008, 0.010, 0.0105, 0.0002], hours_utc=[22, 23, 0, 1],
    )
    assert hourly[3] == 0.0002


def test_first_timestep_of_window_is_missing_when_not_hour_one():
    hourly, anomalies = deaccumulate_era5_land_precipitation_m(values=[0.005], hours_utc=[5])
    assert hourly == [None]
    assert anomalies == []


def test_first_timestep_of_window_is_usable_when_exactly_hour_one():
    # No earlier data is needed for a fresh-cycle hour, even as the very
    # first timestep of the whole request.
    hourly, _ = deaccumulate_era5_land_precipitation_m(values=[0.0003], hours_utc=[1])
    assert hourly == [0.0003]


def test_missing_value_propagates_as_none_not_zero():
    hourly, _ = deaccumulate_era5_land_precipitation_m(
        values=[0.001, None, 0.005], hours_utc=[2, 3, 4],
    )
    # index0: first timestep, hour!=1 -> None (no predecessor)
    # index1: raw itself missing -> None
    # index2: predecessor (index1) missing -> None (propagates forward)
    assert hourly == [None, None, None]


def test_nan_value_treated_the_same_as_none():
    hourly, _ = deaccumulate_era5_land_precipitation_m(
        values=[0.001, float("nan"), 0.005], hours_utc=[2, 3, 4],
    )
    assert hourly == [None, None, None]


def test_unexpected_within_cycle_decrease_is_clamped_and_flagged_not_dropped():
    # hour 6 (index1) decreases relative to hour 5 (index0) without being a
    # fresh-cycle hour — physically impossible, must clamp to 0 AND be
    # reported in the anomaly list, never silently vanish.
    hourly, anomalies = deaccumulate_era5_land_precipitation_m(
        values=[0.010, 0.0095, 0.0110], hours_utc=[5, 6, 7],
    )
    assert hourly[1] == 0.0
    assert anomalies == [1]
    # the following step still diffs against the ORIGINAL raw value (0.0095),
    # not the clamped 0.0, since the underlying accumulation wasn't altered
    assert round(hourly[2], 10) == round(0.0110 - 0.0095, 10)


def test_mismatched_lengths_raises():
    try:
        deaccumulate_era5_land_precipitation_m(values=[0.1, 0.2], hours_utc=[1])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_empty_input():
    assert deaccumulate_era5_land_precipitation_m([], []) == ([], [])


def test_matches_real_pilot_sequence_at_day1_to_day2_boundary():
    """
    Regression test locked to values actually read from the real pilot
    download (data/raw/era5_land/era5_land_pilot_202306.nc, point nearest
    13.4N 77.7E, hours 22/23 of 2023-06-01 and 00/01 of 2023-06-02) —
    not synthetic, hand-verified against the file directly.
    """
    hourly, anomalies = deaccumulate_era5_land_precipitation_m(
        values=[0.01048301, 0.01055341, 0.01074445, 0.00007067],
        hours_utc=[22, 23, 0, 1],
    )
    assert hourly[0] is None  # first timestep of this slice, hour != 1
    assert hourly[1] == 0.01055341 - 0.01048301
    assert hourly[2] == 0.01074445 - 0.01055341  # 00 UTC: plain diff, not a reset
    assert hourly[3] == 0.00007067  # 01 UTC: fresh cycle, raw value as-is
    assert anomalies == []
