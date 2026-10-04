"""Shared test helpers (no network): fake Open-Meteo bodies/responses and stub providers."""

from datetime import date, timedelta

import httpx

from app.weather.errors import ProviderError
from app.weather.schemas import DailyWeather, PointForecast


def open_meteo_body(n=3, first="2026-10-05", offset=19800, tz="Asia/Kolkata", elevation=929.0, nulls=(), units=True, **overrides):
    start = date.fromisoformat(first)
    times = [(start + timedelta(days=i)).isoformat() for i in range(n)]
    body = {"latitude": 13.4, "longitude": 77.75, "elevation": elevation, "utc_offset_seconds": offset, "timezone": tz,
            "daily": {"time": times,
                      "temperature_2m_max": [30.0 + i for i in range(n)], "temperature_2m_min": [20.0 + i for i in range(n)],
                      "precipitation_sum": [1.0] * n, "windspeed_10m_max": [10.0] * n, "relative_humidity_2m_mean": [70.0] * n}}
    if units:
        body["daily_units"] = {"temperature_2m_max": "°C", "temperature_2m_min": "°C", "precipitation_sum": "mm",
                               "windspeed_10m_max": "km/h", "relative_humidity_2m_mean": "%"}
    for i in nulls:
        for k in ("temperature_2m_max", "temperature_2m_min", "precipitation_sum", "windspeed_10m_max", "relative_humidity_2m_mean"):
            body["daily"][k][i] = None
    body.update(overrides)
    return body


class FakeResponse:
    def __init__(self, payload=None, status=200, json_error=False):
        self._payload, self.status_code, self._json_error = payload, status, json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            req = httpx.Request("GET", "https://api.open-meteo.com/v1/forecast")
            raise httpx.HTTPStatusError(f"HTTP {self.status_code}", request=req, response=httpx.Response(self.status_code, request=req))

    def json(self):
        if self._json_error:
            raise ValueError("Expecting value")
        return self._payload


def live_forecast(n=7, first="2026-10-05", elevation=929.0, **kw) -> PointForecast:
    start = date.fromisoformat(first)
    daily = [DailyWeather(date=start + timedelta(days=i), temperature_min_c=20.0, temperature_max_c=30.0, rainfall_mm=2.0,
                          humidity_pct=70.0, wind_kmph=10.0) for i in range(n)]
    base = dict(latitude=13.4, longitude=77.73, elevation_m=elevation, source="open-meteo", is_mocked=False, data_origin="live_provider",
                retrieved_at="2026-10-04T10:00:00Z", timezone="Asia/Kolkata", utc_offset_seconds=19800,
                requested_days=n, forecast_horizon_days=n, daily=daily)
    base.update(kw)
    return PointForecast(**base)


class StubProvider:
    """A stand-in for the live provider: returns a forecast or raises, and counts calls."""
    name = "open-meteo"

    def __init__(self, result=None, error: Exception | None = None):
        self.result, self.error, self.calls = result, error, 0

    def get_forecast(self, latitude, longitude, days):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result if self.result is not None else live_forecast(n=days)


def provider_error(kind="timeout", msg="boom", status=None):
    return ProviderError(msg, kind=kind, upstream_status=status)
