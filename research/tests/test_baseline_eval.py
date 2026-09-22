import pandas as pd

from pipeline.baseline_eval import (
    MIN_SAMPLE_SIZE,
    evaluate_block_as_is,
    evaluate_elevation_temperature_baseline,
    evaluate_predictions,
)


def test_evaluate_predictions_known_mae_rmse():
    # actual - predicted = [1, -1, 2] -> MAE = 4/3, RMSE = sqrt((1+1+4)/3)
    result = evaluate_predictions(actual=[10, 10, 10], predicted=[9, 11, 8])
    assert result["n"] == 3
    assert round(result["mae"], 4) == round((1 + 1 + 2) / 3, 4)
    assert round(result["rmse"], 4) == round(((1 ** 2 + 1 ** 2 + 2 ** 2) / 3) ** 0.5, 4)


def test_evaluate_predictions_perfect_match_is_zero_error():
    result = evaluate_predictions(actual=[5, 6, 7], predicted=[5, 6, 7])
    assert result["mae"] == 0.0
    assert result["rmse"] == 0.0


def test_evaluate_predictions_flags_insufficient_sample_below_threshold():
    result = evaluate_predictions(actual=[1, 2, 3], predicted=[1, 2, 4])
    assert len(result) is not None
    assert result["n"] == 3
    assert result["n"] < MIN_SAMPLE_SIZE
    assert result["insufficient_sample"] is True
    assert "note" in result


def test_evaluate_predictions_zero_samples_reports_none_not_zero():
    result = evaluate_predictions(actual=[], predicted=[])
    assert result["n"] == 0
    assert result["mae"] is None
    assert result["rmse"] is None
    assert result["insufficient_sample"] is True


def test_evaluate_predictions_mismatched_lengths_raises():
    try:
        evaluate_predictions(actual=[1, 2], predicted=[1])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_evaluate_block_as_is_uses_coarse_value_as_prediction():
    pairs = pd.DataFrame({
        "variable": ["temperature_c", "temperature_c"],
        "coarse_value": [27.0, 27.0],
        "fine_value": [24.0, 25.0],
    })
    result = evaluate_block_as_is(pairs)
    assert "temperature_c" in result
    assert result["temperature_c"]["n"] == 2
    # errors: 24-27=-3, 25-27=-2 -> MAE = 2.5
    assert result["temperature_c"]["mae"] == 2.5


def test_evaluate_block_as_is_empty_input_returns_empty_dict():
    empty = pd.DataFrame(columns=["variable", "coarse_value", "fine_value"])
    assert evaluate_block_as_is(empty) == {}


def test_evaluate_elevation_temperature_baseline_applies_lapse_rate():
    from app.downscaling.baseline import TEMPERATURE_LAPSE_RATE_C_PER_M

    pairs = pd.DataFrame({
        "variable": ["temperature_c"],
        "coarse_value": [27.0],
        "fine_value": [27.0 - TEMPERATURE_LAPSE_RATE_C_PER_M * 464.0],  # exact physics, zero error
        "elevation_delta_m": [464.0],
    })
    result = evaluate_elevation_temperature_baseline(pairs)
    assert result["temperature_c"]["mae"] == 0.0


def test_evaluate_elevation_temperature_baseline_ignores_other_variables():
    pairs = pd.DataFrame({
        "variable": ["rainfall_mm"],
        "coarse_value": [10.0],
        "fine_value": [12.0],
        "elevation_delta_m": [464.0],
    })
    result = evaluate_elevation_temperature_baseline(pairs)
    assert result["temperature_c"]["n"] == 0
    assert result["temperature_c"]["insufficient_sample"] is True
