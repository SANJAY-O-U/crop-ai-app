"""
Real weather provider — Open-Meteo (https://open-meteo.com).

Chosen for Phase 1 because it needs no API key and no account, works globally
by lat/lon, and is realistically accessible for development/demo use. It is
NOT a government/IMD data source — swap this out once official block-level
forecasts are wired up. Nothing outside this file knows or cares which
provider is active (see app/weather/base.py).
"""

import httpx

from app.weather.schemas import DailyWeather, PointForecast

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

_DAILY_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "windspeed_10m_max",
    "relative_humidity_2m_mean",
]


class OpenMeteoProvider:
    name = "open-meteo"

    def __init__(self, timeout_s: float = 8.0):
        self._timeout_s = timeout_s

    def get_forecast(self, latitude: float, longitude: float, days: int) -> PointForecast:
        days = max(1, min(days, 16))  # Open-Meteo's free tier caps forecast_days at 16
        resp = httpx.get(
            FORECAST_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "daily": ",".join(_DAILY_VARS),
                "timezone": "auto",
                "forecast_days": days,
            },
            timeout=self._timeout_s,
        )
        resp.raise_for_status()
        body = resp.json()
        daily = body["daily"]

        return PointForecast(
            latitude=body.get("latitude", latitude),
            longitude=body.get("longitude", longitude),
            elevation_m=body.get("elevation"),
            source=self.name,
            is_mocked=False,
            daily=[
                DailyWeather(
                    date=daily["time"][i],
                    temperature_min_c=daily["temperature_2m_min"][i],
                    temperature_max_c=daily["temperature_2m_max"][i],
                    rainfall_mm=daily["precipitation_sum"][i],
                    humidity_pct=daily["relative_humidity_2m_mean"][i],
                    wind_kmph=daily["windspeed_10m_max"][i],
                )
                for i in range(len(daily["time"]))
            ],
        )
