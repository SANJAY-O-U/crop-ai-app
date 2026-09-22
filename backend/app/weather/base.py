"""
WeatherProvider interface — the abstraction that keeps the rest of CropCast
independent of any single weather data source.

To add a new provider (e.g. IMD once access is arranged), implement this
Protocol and register it in service.py. Nothing else needs to change.
"""

from typing import Protocol
from app.weather.schemas import PointForecast


class WeatherProvider(Protocol):
    name: str

    def get_forecast(self, latitude: float, longitude: float, days: int) -> PointForecast:
        """Return a normalized forecast for a single point. Must raise on failure
        (network error, bad response) rather than silently returning empty data —
        callers decide how to handle/fallback on failure, the provider should not."""
        ...
