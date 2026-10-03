"""
Stage 5 PRE-DECLARED criteria. Written before any observation VALUE was
downloaded or inspected (only station metadata had been read). Everything
below is applied mechanically; nothing is chosen after seeing results.

Framing: Stage 4D was evaluated against the ERA5-Land reanalysis proxy.
Stage 5 evaluates the frozen Stage 4D model against independent observations.
"""

# ---- evaluation period --------------------------------------------------
# Only the Stage 4D TEST year: the frozen fold models never saw these hours.
EVAL_START_UTC = "2023-01-01T00:00Z"
EVAL_END_UTC = "2023-12-31T23:00Z"

# ---- station eligibility (metadata only) --------------------------------
# A station is a candidate if the ISD station history says it reports across
# the whole evaluation year.
REQUIRE_METADATA_COVERAGE = ("20230101", "20231231")

# PRIMARY matched set: the station point lies INSIDE the union of the
# included (COMPLETE, land-target) Panchayat polygons of one selected Stage 4
# area, AND its nearest ERA5-Land cell is one of that area's included target
# cells. It is then compared with the Stage 4D output for the Panchayat whose
# polygon contains it (that Panchayat's ERA5-Land target cell and static
# features) -- never presented as a Panchayat-average observation.
# NEARBY DIAGNOSTIC set (reported separately, never pooled with primary):
# not primary, but its nearest ERA5-Land cell is an included target cell of
# a selected area or within ADJACENT_CELLS (Chebyshev) of one. It is compared
# with the Panchayat of that area whose centroid is nearest to the station.
ADJACENT_CELLS = 1
# Yelandur is the frozen Phase 2D reference, not Stage 4 geography: stations
# matching only Yelandur cells are excluded from both sets.

# ---- observation acceptance ---------------------------------------------
# ISD quality codes accepted (format document): 0,1,4,5,9 = passed checks;
# A = flagged suspect but accepted by NCEI. Rejected: 2,3,6,7 (suspect /
# erroneous) and any other code. Rejected values are recorded, not deleted.
ACCEPTED_QC = {"0", "1", "4", "5", "9", "A"}
# Report timing: an observation is aligned to a Stage 4 UTC hour only if it
# is at an exact top-of-hour time (minute == 0). Off-hour reports are
# recorded and not used (no rounding, no interpolation). If several
# accepted reports share a UTC hour, the one listed first by NCEI is used and
# the duplicates are recorded.

# ---- variable mapping ---------------------------------------------------
# temperature_c   ISD TMP degC (x10)            -> degC, no conversion beyond scaling
# dewpoint_c      ISD DEW degC (x10)            -> degC
# relative_hum.   derived from observed TMP+DEW with the SAME formula the
#                 pipeline uses (pipeline.units.relative_humidity_pct); only
#                 when both are accepted at that hour
# wind_speed_kmph ISD WND speed m/s (x10) * 3.6 -> km/h; ISD wind is the
#                 standard 10 m surface wind for WMO stations (height not
#                 carried per record; recorded as a limitation)
# rainfall_mm     ISD AA1-AA4: depth mm (x10) over an explicit period of P
#                 hours ending at the report time. Compared ONLY with the
#                 SUM of the method's hourly rainfall over the same P hours
#                 ending at the report hour, and only if all P model hours
#                 exist. Trace (condition 2) -> 0.0 mm and flagged; periods
#                 with condition 1,3,5,6,7,8,E,I,J are not used. Different
#                 periods are analysed separately; never cumulative vs hourly.
RAIN_ACCEPTED_PERIODS_H = (1, 3, 6, 12, 24)
RAIN_WET_THRESHOLD_MM_PER_H = 0.1  # applied as 0.1 mm x P hours for a P-hour period

# ---- physical QC limits (flag, never silently drop) ---------------------
QC_LIMITS = {"temperature_c": (-5.0, 50.0), "dewpoint_c": (-20.0, 35.0),
             "wind_speed_kmph": (0.0, 150.0), "rainfall_mm_per_h": (0.0, 200.0)}
QC_CONSTANT_RUN_HOURS = 24  # identical consecutive values for >= this many reports -> flagged suspect

# ---- statistics ---------------------------------------------------------
MIN_STATION_HOURS_FOR_METRICS = 500      # below: "insufficient sample size"
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_BLOCK_DAYS = 7                 # moving-block bootstrap within station (time dependence)
BOOTSTRAP_SEED = 20230101
SEASONS = {"DJF": (12, 1, 2), "MAM": (3, 4, 5), "JJAS": (6, 7, 8, 9), "ON": (10, 11)}  # IMD seasons
ELEVATION_BANDS_M = (0, 300, 600, 900, 3000)

# ---- outcome rule per variable (set before any comparison was computed) --
# Using the pooled bootstrap of |e_C4| - |e_baseline| over stations with
# sufficient sample size, for baseline in (A1_bilinear, A2_nearest):
#   SUPPORTED     both 95% intervals entirely < 0   (C4 lower error than both)
#   CONTRADICTED  both 95% intervals entirely > 0   (C4 higher error than both)
#   MIXED         anything else (incl. intervals spanning 0, or opposite signs)
# Stations below MIN_STATION_HOURS_FOR_METRICS are reported but not pooled.
# The label describes ONLY the evaluated stations/period and the diagnostic
# (nearby) station set.
