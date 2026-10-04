"""
Forecast correction strategies: block forecast -> correction strategy -> Panchayat forecast.

Today exactly ONE strategy is enabled in production: "baseline" (the deterministic, uncalibrated elevation heuristic in
baseline.py). "ml_corrected" is a registered but DISABLED placeholder: there is no model, no artifact, no inference
code, and enabling it is impossible by configuration alone. It exists only so a future, validated ML correction can be
added as one new class implementing ForecastCorrectionStrategy without touching the routes, schemas or frontend.

Selecting a method (env DOWNSCALING_METHOD, default "baseline"): a request for a disabled or unknown method is ignored
with a warning and the baseline is used; responses always report the method that was ACTUALLY applied.
"""

import os
from dataclasses import dataclass
from typing import Protocol

from app.downscaling import baseline
from app.observability import log_event
from app.weather.schemas import DailyWeather, PointForecast


class StrategyDisabledError(RuntimeError):
    """The requested correction strategy exists as a placeholder but is not enabled."""


@dataclass(frozen=True)
class CorrectionResult:
    daily: list[DailyWeather]
    adjustment: dict
    method: str
    status: str
    model_version: str | None = None


class ForecastCorrectionStrategy(Protocol):
    method: str
    enabled: bool

    def correct(self, block_forecast: PointForecast, block_elevation_m: float | None,
                panchayat_elevation_m: float | None) -> CorrectionResult: ...


class BaselineStrategy:
    method = "baseline"
    enabled = True

    def correct(self, block_forecast, block_elevation_m, panchayat_elevation_m) -> CorrectionResult:
        meta = baseline.build_adjustment_metadata(block_elevation_m, panchayat_elevation_m)
        daily = baseline.apply_baseline(block_forecast, block_elevation_m, panchayat_elevation_m)
        return CorrectionResult(daily=daily, adjustment=meta, method=self.method, status=meta["status"], model_version=None)


class MLCorrectionStrategy:
    """DISABLED placeholder. Not validated (real-forecast evaluation is not statistically ready); has no model."""
    method = "ml_corrected"
    enabled = False

    def correct(self, block_forecast, block_elevation_m, panchayat_elevation_m) -> CorrectionResult:
        raise StrategyDisabledError("ML correction is not enabled: no validated model exists.")


REGISTRY: dict[str, ForecastCorrectionStrategy] = {"baseline": BaselineStrategy(), "ml_corrected": MLCorrectionStrategy()}
DEFAULT_METHOD = "baseline"


def requested_method() -> str:
    return os.getenv("DOWNSCALING_METHOD", DEFAULT_METHOD).strip().lower() or DEFAULT_METHOD


def active_strategy() -> ForecastCorrectionStrategy:
    wanted = requested_method()
    strategy = REGISTRY.get(wanted)
    if strategy is None or not strategy.enabled:
        log_event("downscaling_method_ignored", level="warning", requested=wanted, active=DEFAULT_METHOD)
        return REGISTRY[DEFAULT_METHOD]
    return strategy


def strategy_status() -> dict:
    wanted, active = requested_method(), active_strategy()
    return {"requested_method": wanted, "active_method": active.method, "ml_correction_enabled": REGISTRY["ml_corrected"].enabled,
            "warning": None if wanted == active.method else f"requested method '{wanted}' is not enabled; using '{active.method}'"}
