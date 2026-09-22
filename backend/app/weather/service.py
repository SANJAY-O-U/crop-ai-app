"""
Provider selection + failure fallback.

Everything outside this module calls get_point_forecast() and never touches
a concrete provider class directly — that's what keeps the provider swappable
(SIH requirement: "do not hard-code the rest of the application to one
weather provider").
"""

import logging
import os

from app.weather.base import WeatherProvider
from app.weather.providers.mock import MockWeatherProvider
from app.weather.providers.open_meteo import OpenMeteoProvider
from app.weather.schemas import PointForecast

logger = logging.getLogger(__name__)

_PROVIDERS: dict[str, WeatherProvider] = {
    "open-meteo": OpenMeteoProvider(),
    "mock": MockWeatherProvider(),
}


def _configured_provider() -> WeatherProvider:
    key = os.getenv("WEATHER_PROVIDER", "open-meteo").strip().lower()
    return _PROVIDERS.get(key, _PROVIDERS["open-meteo"])


def get_point_forecast(latitude: float, longitude: float, days: int) -> PointForecast:
    """
    Fetch a normalized forecast for one point, using the configured provider.
    Falls back to the deterministic mock provider (clearly labeled, never
    silently) if the live provider fails — a demo should never hard-crash
    because an external API timed out.
    """
    provider = _configured_provider()

    if provider.name == "mock":
        return provider.get_forecast(latitude, longitude, days)

    try:
        return provider.get_forecast(latitude, longitude, days)
    except Exception as exc:
        logger.warning(
            "Weather provider '%s' failed (%s) — falling back to mock data.",
            provider.name, exc,
        )
        return _PROVIDERS["mock"].get_forecast(latitude, longitude, days)
