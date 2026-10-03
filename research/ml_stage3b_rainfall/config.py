"""
Pre-specified settings for ML Stage 3B (two-stage rainfall model). All values
here were fixed BEFORE any Stage 3B result was computed; none is tuned on
2023 (test) data.
"""

import pandas as pd

# An hour is "wet" if rainfall > 0.1 mm (common rain-gauge resolution). Used
# for classifier labels, amount-model training rows, and occurrence metrics.
# ERA5-Land has many sub-0.1 mm drizzle hours (57% of hours are > 0 mm but
# only ~17% exceed 0.1 mm), so ">0" would label most hours wet.
WET_THRESHOLD_MM = 0.1

# Occurrence probability threshold: chosen PER FOLD from TRAINING rows only,
# via an inner temporal split of the fold's training period:
#   inner-train : 2021-01-01T00Z .. 2021-12-31T23Z
#   inner gap   : 2022-01-01T00Z .. 2022-01-07T23Z (7 days, unused)
#   inner-val   : 2022-01-08T00Z .. end of the fold's training rows (2022-12-24T23Z)
# The threshold maximizing inner-val F1 over THRESHOLD_GRID is selected
# (ties -> lowest threshold); the classifier is then refit on ALL training rows.
INNER_TRAIN_END_EXCLUSIVE = pd.Timestamp("2022-01-01T00:00", tz="UTC")
INNER_VAL_START = pd.Timestamp("2022-01-08T00:00", tz="UTC")
THRESHOLD_GRID = [round(0.05 * k, 2) for k in range(1, 20)]  # 0.05 .. 0.95

_COMMON = {
    "learning_rate": 0.1,
    "max_iter": 200,
    "max_leaf_nodes": 31,
    "max_depth": None,
    "min_samples_leaf": 200,
    "l2_regularization": 0.0,
    "max_bins": 255,
    "early_stopping": False,
    "random_state": 0,
}

# Stage 1 of the two-stage model: wet/dry classifier.
CLASSIFIER_CONFIG = {"loss": "log_loss", **_COMMON}

# Stage 2: amount on wet hours only. Poisson loss (log link) keeps amount
# predictions strictly positive and suits a skewed, non-negative target.
AMOUNT_CONFIG = {"loss": "poisson", **_COMMON}
