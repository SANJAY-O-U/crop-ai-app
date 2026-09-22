"""
Offline research evaluation ONLY. Does not import, call, or modify anything
under backend/app/downscaling/routes.py or service.py — the live API is
untouched. This module answers "how good is a downscaling method against
the ERA5-Land proxy target", using real MAE/RMSE, and explicitly refuses to
present a metric computed from too few samples as if it were meaningful.
"""

import math
import os
import sys

import pandas as pd

# Import the ACTUAL production constant (not a re-typed copy) so this
# evaluation reflects the real Phase 1 formula, not a drifted duplicate.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
from app.downscaling.baseline import TEMPERATURE_LAPSE_RATE_C_PER_M  # noqa: E402

MIN_SAMPLE_SIZE = 30  # below this, MAE/RMSE is reported but flagged as not meaningful


def _mae(errors: list[float]) -> float:
    return sum(abs(e) for e in errors) / len(errors)


def _rmse(errors: list[float]) -> float:
    return math.sqrt(sum(e ** 2 for e in errors) / len(errors))


def evaluate_predictions(actual: list[float], predicted: list[float]) -> dict:
    """Real MAE/RMSE for one variable's (actual, predicted) pairs — never invented."""
    if len(actual) != len(predicted):
        raise ValueError("actual and predicted must be the same length")

    n = len(actual)
    if n == 0:
        return {
            "n": 0, "mae": None, "rmse": None, "insufficient_sample": True,
            "note": "Zero samples — no metric can be computed.",
        }

    errors = [a - p for a, p in zip(actual, predicted)]
    result = {
        "n": n,
        "mae": round(_mae(errors), 4),
        "rmse": round(_rmse(errors), 4),
        "insufficient_sample": n < MIN_SAMPLE_SIZE,
    }
    if result["insufficient_sample"]:
        result["note"] = (
            f"Only {n} sample(s) — below this pipeline's {MIN_SAMPLE_SIZE}-sample "
            "floor for a minimally meaningful estimate. Treat as illustrative "
            "only, not a validated accuracy claim."
        )
    return result


def evaluate_block_as_is(training_pairs: pd.DataFrame) -> dict:
    """
    Naive baseline: predict panchayat value = block value, unchanged.
    Every other method must be compared against this, or an "improvement"
    claim has no meaning.
    """
    if training_pairs.empty:
        return {}
    results = {}
    for variable, group in training_pairs.groupby("variable"):
        results[variable] = evaluate_predictions(
            actual=group["fine_value"].tolist(),
            predicted=group["coarse_value"].tolist(),
        )
    return results


def evaluate_elevation_temperature_baseline(training_pairs: pd.DataFrame) -> dict:
    """
    Evaluates the SAME physical lapse-rate formula
    backend/app/downscaling/baseline.py uses for temperature, using the
    imported production constant. Applied directly here rather than routed
    through the production Pydantic schema, because that schema is shaped
    around daily min/max forecast objects, not ERA5-Land hourly points —
    reshaping this offline evaluation into that schema would add coupling
    for no benefit while nothing here touches the live API either way.

    Only defined for variable == "temperature_c": the lapse rate has no
    established physical meaning for rainfall/humidity/wind (see the
    Phase 1.5 report) — do not attempt to extend this to other variables.
    """
    subset = training_pairs[training_pairs["variable"] == "temperature_c"]
    if subset.empty:
        return {
            "temperature_c": {
                "n": 0, "mae": None, "rmse": None, "insufficient_sample": True,
                "note": "No temperature_c rows in this training-pair set.",
            }
        }

    predicted = subset["coarse_value"] - TEMPERATURE_LAPSE_RATE_C_PER_M * subset["elevation_delta_m"]
    return {
        "temperature_c": evaluate_predictions(
            actual=subset["fine_value"].tolist(),
            predicted=predicted.tolist(),
        )
    }
