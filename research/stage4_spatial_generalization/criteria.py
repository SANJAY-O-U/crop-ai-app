"""
Pre-specified feasibility criteria for Stage 4 candidate regions. Fixed
BEFORE the statewide audit was run; the audit applies them mechanically.

Candidate unit: an LGD Taluka Panchayat (the same PRI tier as Yelandur,
code 6132), audited for every Taluka Panchayat in Karnataka.
"""

# Frozen Phase 2D experiment: the 4 ERA5-Land cells used by Yelandur's
# COMPLETE GPs (from research/era5_linkage/yelandur_era5_linkage.json).
YELANDUR_TALUKA_PANCHAYAT_CODE = "6132"

# A candidate is RECOMMENDED for the shortlist only if ALL hold:
MIN_COMPLETE_GP_SHARE = 0.80        # >= 80% of its LGD GPs have a COMPLETE spatial proxy
MIN_NEW_CELL_GROUPS = 3             # >= 3 ERA5-Land cells (with >=1 COMPLETE GP) not used by Yelandur
MIN_DISTANCE_FROM_YELANDUR_KM = 50  # candidate centroid >= 50 km (~5 ERA5-Land cells) from Yelandur's

# Flags that downgrade an otherwise-passing candidate to CONDITIONAL:
#  - a new cell centre falls outside every Karnataka DataMeet village polygon
#    (possible sea cell for ERA5-Land's land-only grid, or another state's
#    territory -- the ERA5-Land land-sea mask has not been checked offline);
#  - any COMPLETE GP contains a village LGD maps to more than one GP.
# Candidates failing any RECOMMEND criterion are EXCLUDED with the reason(s).

# Grid neighbourhood used to count cells "adjacent" to Yelandur's cells
# (Chebyshev distance in cells).
ADJACENT_CELL_RADIUS = 1
