from typing import Literal

from pydantic import BaseModel, Field

from app.weather.schemas import DailyWeather, DataOrigin, PointForecast

DownscalingMethod = Literal["baseline", "ml_corrected"]

DAY_DEFINITION = ("Local calendar date at the forecast point in the provider's timezone (Open-Meteo timezone=auto, "
                  "Asia/Kolkata UTC+05:30 for the pilot). Dates are passed through unchanged from provider to Panchayat forecast.")


class Provenance(BaseModel):
    """Answers: where did the weather come from, was it real or fallback, when, which day definition, which correction,
    was elevation available. Additive: the frontend does not need to display any of it."""
    weather_source: str
    data_origin: DataOrigin
    is_mocked: bool
    fallback_used: bool
    fallback_reason: str | None = None
    retrieved_at: str | None = None
    from_cache: bool = False
    timezone: str | None = None
    day_definition: str = DAY_DEFINITION
    forecast_horizon_days: int | None = None
    partial: bool = False
    omitted_dates: list[str] = Field(default_factory=list)
    correction_method: DownscalingMethod
    correction_status: str          # applied | elevation_unavailable | elevation_invalid | elevation_delta_implausible
    model_version: str | None = None
    block_elevation_m: float | None = None
    panchayat_elevation_m: float | None = None
    elevation_available: bool
    ml_correction_enabled: bool = False
    research_data_used: bool = False   # always false: nothing under research/ feeds production responses


class DownscaledForecast(BaseModel):
    panchayat_id: str
    panchayat_name: str
    block_id: str
    block_name: str
    method: DownscalingMethod
    model_version: str | None = None   # null: the baseline has no trained model
    block_source: PointForecast
    adjustment: dict
    daily: list[DailyWeather]
    provenance: Provenance | None = None
