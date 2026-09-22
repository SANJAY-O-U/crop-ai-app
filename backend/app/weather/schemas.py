"""
Normalized weather data structures shared by every WeatherProvider implementation.

Any provider (Open-Meteo today, IMD or another service later) must return data
shaped like this. Nothing outside app/weather/ should ever see a provider's
raw response format.
"""

from datetime import date as Date
from pydantic import BaseModel, Field


class DailyWeather(BaseModel):
    date: Date
    temperature_min_c: float
    temperature_max_c: float
    rainfall_mm: float = Field(ge=0)
    humidity_pct: float = Field(ge=0, le=100)
    wind_kmph: float = Field(ge=0)


class PointForecast(BaseModel):
    """A forecast for a single lat/lon point, as returned by a WeatherProvider."""
    latitude: float
    longitude: float
    elevation_m: float | None = None
    source: str          # e.g. "open-meteo", "mock"
    is_mocked: bool = False
    daily: list[DailyWeather]
