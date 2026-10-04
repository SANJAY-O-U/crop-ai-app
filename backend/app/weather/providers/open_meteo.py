"""
Real weather provider — Open-Meteo (https://open-meteo.com).

Chosen for Phase 1 because it needs no API key and no account, works globally
by lat/lon, and is realistically accessible for development/demo use. It is
NOT a government/IMD data source — swap this out once official block-level
forecasts are wired up. Nothing outside this file knows or cares which
provider is active (see app/weather/base.py).

Reliability contract (Production Candidate V1):
  * bounded timeouts (connect 3 s / read 8 s) and at most ONE conservative retry, only for connect-level failures and
    5xx responses, after a fixed 0.3 s pause. Read timeouts, 4xx responses and bad payloads are never retried, so the
    worst case is ~8 s (read timeout) or ~6.3 s (two connect timeouts).
  * every failure is raised as a typed ProviderError (app/weather/errors.py) -- never returned as weather.
  * a day whose values include null (Open-Meteo returns nulls at the end of the 16-day horizon) is OMITTED and
    listed in `omitted_dates`; it is never filled or interpolated. Values outside physical bounds, malformed
    shapes, duplicate/unsorted dates, unexpected units and an empty result reject the whole response.
  * the request parameters are unchanged: the research forecast archive reuses them (see its parity test).
"""

import math
import time
from datetime import datetime, timezone

import httpx
from pydantic import ValidationError

from app.weather.errors import ProviderError, ProviderResponseError, ProviderTimeoutError, ProviderUnavailableError
from app.weather.schemas import DailyWeather, PointForecast

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

_DAILY_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "windspeed_10m_max",
    "relative_humidity_2m_mean",
]

_EXPECTED_UNITS = {
    "temperature_2m_max": "°C", "temperature_2m_min": "°C", "precipitation_sum": "mm",
    "windspeed_10m_max": "km/h", "relative_humidity_2m_mean": "%",
}

CONNECT_TIMEOUT_S = 3.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _number(value, name: str, date_str: str):
    """None -> None (a null day); a finite real number -> float; anything else is a malformed payload."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProviderResponseError(f"non-numeric '{name}' value for {date_str}", kind="malformed_response")
    if not math.isfinite(value):
        raise ProviderResponseError(f"non-finite '{name}' value for {date_str}", kind="invalid_payload")
    return float(value)


class OpenMeteoProvider:
    name = "open-meteo"

    def __init__(self, timeout_s: float = 8.0, retries: int = 1, backoff_s: float = 0.3):
        self._timeout_s = timeout_s
        self._retries = max(0, min(retries, 2))        # hard cap: never hammer the provider
        self._backoff_s = backoff_s

    # ------------------------------------------------------------------------------------------------
    def _fetch(self, params: dict) -> dict:
        timeout = httpx.Timeout(self._timeout_s, connect=min(CONNECT_TIMEOUT_S, self._timeout_s))
        last: ProviderError | None = None
        for attempt in range(self._retries + 1):
            if attempt:
                time.sleep(self._backoff_s)
            try:
                resp = httpx.get(FORECAST_URL, params=params, timeout=timeout)
                resp.raise_for_status()
                try:
                    return resp.json()
                except ValueError as exc:
                    raise ProviderResponseError(f"response is not valid JSON ({type(exc).__name__})", kind="malformed_response") from exc
            except ProviderError as exc:                       # malformed JSON: not retried
                raise exc
            except httpx.TimeoutException as exc:
                last = ProviderTimeoutError(f"timed out after {self._timeout_s:g}s")
                last.__cause__ = exc
                if not isinstance(exc, httpx.ConnectTimeout):   # a read timeout already cost the full budget: do not double it
                    raise last
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else None
                last = ProviderResponseError(f"HTTP {status}", kind="http_error", upstream_status=status)
                last.__cause__ = exc
                if status is not None and status < 500:        # client errors will not improve on retry
                    raise last
            except Exception as exc:                           # httpx.RequestError and anything else network-like
                last = ProviderUnavailableError(f"{type(exc).__name__}: {exc}"[:200])
                last.__cause__ = exc
        raise last

    # ------------------------------------------------------------------------------------------------
    def get_forecast(self, latitude: float, longitude: float, days: int) -> PointForecast:
        requested = max(1, min(days, 16))  # Open-Meteo's free tier caps forecast_days at 16
        body = self._fetch({
            "latitude": latitude,
            "longitude": longitude,
            "daily": ",".join(_DAILY_VARS),
            "timezone": "auto",
            "forecast_days": requested,
        })
        retrieved_at = _utc_now_iso()

        if not isinstance(body, dict) or not isinstance(body.get("daily"), dict):
            raise ProviderResponseError("response has no 'daily' block", kind="malformed_response")
        daily = body["daily"]
        times = daily.get("time")
        if not isinstance(times, list):
            raise ProviderResponseError("'daily.time' missing", kind="malformed_response")
        for var in _DAILY_VARS:
            if not isinstance(daily.get(var), list) or len(daily[var]) != len(times):
                raise ProviderResponseError(f"daily variable '{var}' missing or length differs from 'time'", kind="malformed_response")

        units = body.get("daily_units")
        if isinstance(units, dict):
            for var, expected in _EXPECTED_UNITS.items():
                if var in units and units[var] != expected:
                    raise ProviderResponseError(f"unexpected unit for {var}: {units[var]!r} (expected {expected!r})", kind="unexpected_units")

        days_out, omitted, seen = [], [], []
        for i, date_str in enumerate(times):
            try:
                parsed = datetime.strptime(str(date_str), "%Y-%m-%d").date()
            except ValueError as exc:
                raise ProviderResponseError(f"invalid date {date_str!r}", kind="malformed_response") from exc
            if seen and parsed <= seen[-1]:
                raise ProviderResponseError("dates are duplicated or not ascending", kind="malformed_response")
            seen.append(parsed)
            values = {var: _number(daily[var][i], var, str(date_str)) for var in _DAILY_VARS}
            if any(v is None for v in values.values()):
                omitted.append(str(date_str))          # provider has no value for this day: omit, never fill
                continue
            try:
                days_out.append(DailyWeather(
                    date=parsed,
                    temperature_min_c=values["temperature_2m_min"],
                    temperature_max_c=values["temperature_2m_max"],
                    rainfall_mm=values["precipitation_sum"],
                    humidity_pct=values["relative_humidity_2m_mean"],
                    wind_kmph=values["windspeed_10m_max"],
                ))
            except ValidationError as exc:
                raise ProviderResponseError(f"values for {date_str} outside physical bounds", kind="invalid_payload") from exc

        if not days_out:
            raise ProviderResponseError("provider returned no usable forecast days", kind="empty_forecast")

        try:
            forecast = PointForecast(
                latitude=body.get("latitude", latitude),
                longitude=body.get("longitude", longitude),
                elevation_m=body.get("elevation"),
                source=self.name,
                is_mocked=False,
                data_origin="live_provider",
                retrieved_at=retrieved_at,
                forecast_generated_at=None,
                timezone=body.get("timezone"),
                utc_offset_seconds=body.get("utc_offset_seconds"),
                requested_days=requested,
                forecast_horizon_days=len(days_out),
                partial=bool(omitted) or len(days_out) < requested,
                omitted_dates=omitted,
                daily=days_out,
            )
        except ValidationError as exc:
            raise ProviderResponseError("response failed schema validation", kind="invalid_payload") from exc
        return forecast
