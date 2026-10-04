"""
Normalized weather data structures shared by every WeatherProvider implementation.

Any provider (Open-Meteo today, IMD or another service later) must return data
shaped like this. Nothing outside app/weather/ should ever see a provider's
raw response format.

Canonical day definition (see docs/PRODUCTION_READINESS.md): `DailyWeather.date` is the LOCAL calendar date at the
forecast point in the provider's timezone (Open-Meteo `timezone=auto`, i.e. Asia/Kolkata, UTC+05:30, for the pilot).
Dates are passed through unchanged -- nothing in CropCast shifts UTC timestamps into days.

Provenance fields added in Production Candidate V1 are all optional/additive, so existing consumers keep working.
"""

from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Physical sanity bounds: generous enough to admit real extremes, tight enough to reject corrupt payloads.
TEMPERATURE_BOUNDS_C = (-90.0, 60.0)
MAX_RAINFALL_MM_PER_DAY = 2000.0        # world record is ~1,800 mm/day
MAX_WIND_KMPH = 500.0
ELEVATION_BOUNDS_M = (-500.0, 9000.0)

DataOrigin = Literal["live_provider", "mock_configured", "mock_fallback"]


class DailyWeather(BaseModel):
    date: Date
    temperature_min_c: float = Field(ge=TEMPERATURE_BOUNDS_C[0], le=TEMPERATURE_BOUNDS_C[1])
    temperature_max_c: float = Field(ge=TEMPERATURE_BOUNDS_C[0], le=TEMPERATURE_BOUNDS_C[1])
    rainfall_mm: float = Field(ge=0, le=MAX_RAINFALL_MM_PER_DAY)
    humidity_pct: float = Field(ge=0, le=100)
    wind_kmph: float = Field(ge=0, le=MAX_WIND_KMPH)

    @model_validator(mode="after")
    def _min_not_above_max(self):
        if self.temperature_min_c > self.temperature_max_c:
            raise ValueError("temperature_min_c is above temperature_max_c")
        return self


class PointForecast(BaseModel):
    """A forecast for a single lat/lon point, as returned by a WeatherProvider."""
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    elevation_m: float | None = None
    source: str          # e.g. "open-meteo", "mock"
    is_mocked: bool = False
    daily: list[DailyWeather]

    # --- provenance (additive) -------------------------------------------------------------------------
    data_origin: DataOrigin = "live_provider"     # REAL provider response vs configured mock vs fallback after a failure
    fallback_reason: str | None = None            # set only when data_origin == "mock_fallback"
    retrieved_at: str | None = None               # UTC ISO-8601 time the provider response was received
    forecast_generated_at: str | None = None      # provider model-run time; Open-Meteo does not expose it -> null
    timezone: str | None = None                   # provider timezone name defining the daily dates, e.g. "Asia/Kolkata"
    utc_offset_seconds: int | None = None
    requested_days: int | None = None
    forecast_horizon_days: int | None = None      # number of daily records actually returned
    partial: bool = False                         # True if fewer valid days than requested were returned
    omitted_dates: list[str] = Field(default_factory=list)   # dates the provider returned with null values (dropped, not filled)
    from_cache: bool = False
    cache_age_s: int | None = None

    @field_validator("elevation_m")
    @classmethod
    def _elevation_in_range_or_none(cls, v):
        # An absurd elevation is dropped to None (unknown) rather than failing the whole forecast.
        if v is None or ELEVATION_BOUNDS_M[0] <= v <= ELEVATION_BOUNDS_M[1]:
            return v
        return None

    @model_validator(mode="after")
    def _dates_unique_and_ascending(self):
        dates = [d.date for d in self.daily]
        if any(b <= a for a, b in zip(dates, dates[1:])):
            raise ValueError("daily dates must be unique and strictly ascending")
        return self
