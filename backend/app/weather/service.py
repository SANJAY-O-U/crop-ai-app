"""
Provider selection, failure handling, a small bounded cache.

Everything outside this module calls get_point_forecast() and never touches
a concrete provider class directly — that's what keeps the provider swappable
(SIH requirement: "do not hard-code the rest of the application to one
weather provider").

Environment (all optional):
  WEATHER_PROVIDER          open-meteo (default) | mock
  WEATHER_FALLBACK          mock (default, backward compatible) | error
                            What to do when the live provider fails. "mock" returns the deterministic mock forecast
                            EXPLICITLY labelled (is_mocked=true, data_origin="mock_fallback", fallback_reason=...).
                            "error" raises WeatherUnavailableError, which the API maps to HTTP 503/502. Recommended
                            for production deployments that must never show synthetic numbers.
  WEATHER_CACHE_TTL_S       successful LIVE responses are reused for this long (default 600; 0 disables)
  WEATHER_FAILURE_COOLDOWN_S after a provider failure, the provider is not called again for this long (default 30)

Only successful live responses are cached, and a cached response keeps its original retrieved_at (+ from_cache,
cache_age_s), so a stale forecast is never presented as freshly retrieved. Mock/fallback data is never cached.
"""

import os
import threading
import time
from collections import OrderedDict

from app.observability import count, log_event
from app.weather.base import WeatherProvider
from app.weather.errors import ProviderError, WeatherUnavailableError
from app.weather.providers.mock import MockWeatherProvider
from app.weather.providers.open_meteo import OpenMeteoProvider
from app.weather.schemas import PointForecast

_PROVIDERS: dict[str, WeatherProvider] = {
    "open-meteo": OpenMeteoProvider(),
    "mock": MockWeatherProvider(),
}
_MAX_CACHE_ENTRIES = 64

_lock = threading.Lock()
_cache: "OrderedDict[tuple, tuple[float, PointForecast]]" = OrderedDict()
_recent_failures: dict[tuple, tuple[float, ProviderError]] = {}
_status = {"last_success_at": None, "last_failure_at": None, "last_failure_kind": None}


def configured_provider_name() -> str:
    return os.getenv("WEATHER_PROVIDER", "open-meteo").strip().lower()


def _configured_provider() -> WeatherProvider:
    return _PROVIDERS.get(configured_provider_name(), _PROVIDERS["open-meteo"])


def fallback_policy() -> str:
    return "error" if os.getenv("WEATHER_FALLBACK", "mock").strip().lower() == "error" else "mock"


def _float_env(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, default)))
    except ValueError:
        return default


def provider_status() -> dict:
    """Operational snapshot used by /ready. Informational only: readiness does not depend on the provider being up."""
    return {"configured_provider": configured_provider_name(), "provider_known": configured_provider_name() in _PROVIDERS,
            "fallback_policy": fallback_policy(), **_status}


def clear_state() -> None:
    """Test helper: forget cached forecasts and recent failures."""
    with _lock:
        _cache.clear()
        _recent_failures.clear()
        _status.update(last_success_at=None, last_failure_at=None, last_failure_kind=None)


def _key(provider_name: str, lat: float, lon: float, days: int) -> tuple:
    return (provider_name, round(lat, 4), round(lon, 4), days)


def _utc_stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _fallback(lat: float, lon: float, days: int, error: ProviderError, cooldown: bool = False) -> PointForecast:
    mock = _PROVIDERS["mock"].get_forecast(lat, lon, days)
    reason = error.reason + (" (provider in failure cooldown)" if cooldown else "")
    count("weather_fallback_used")
    log_event("weather_fallback_used", level="warning", reason_kind=error.kind, cooldown=cooldown, lat=round(lat, 3), lon=round(lon, 3))
    return mock.model_copy(update={"data_origin": "mock_fallback", "fallback_reason": reason})


def get_point_forecast(latitude: float, longitude: float, days: int) -> PointForecast:
    """
    Fetch a normalized forecast for one point using the configured provider.

    Returns a real provider forecast, a cached real forecast (with its original retrieved_at), the configured mock, or —
    only if WEATHER_FALLBACK=mock — an explicitly labelled mock fallback. With WEATHER_FALLBACK=error a provider failure
    raises WeatherUnavailableError instead. A provider failure is never returned as apparently real weather.
    """
    provider = _configured_provider()

    if provider.name == "mock":
        return provider.get_forecast(latitude, longitude, days)

    key = _key(provider.name, latitude, longitude, days)
    ttl, cooldown_s = _float_env("WEATHER_CACHE_TTL_S", 600), _float_env("WEATHER_FAILURE_COOLDOWN_S", 30)
    now = time.monotonic()

    with _lock:
        hit = _cache.get(key)
        if hit and ttl and now - hit[0] <= ttl:
            _cache.move_to_end(key)
            age = int(now - hit[0])
            log_event("weather_cache_hit", age_s=age, days=days)
            return hit[1].model_copy(update={"from_cache": True, "cache_age_s": age})
        failure = _recent_failures.get(key)
        in_cooldown = bool(failure and cooldown_s and now - failure[0] <= cooldown_s)

    if in_cooldown:
        if fallback_policy() == "error":
            raise WeatherUnavailableError(failure[1])
        return _fallback(latitude, longitude, days, failure[1], cooldown=True)

    t0 = time.monotonic()
    try:
        forecast = provider.get_forecast(latitude, longitude, days)
    except ProviderError as exc:
        latency = round((time.monotonic() - t0) * 1000)
        count("weather_provider_failure")
        if exc.kind in ("malformed_response", "invalid_payload", "unexpected_units", "empty_forecast"):
            count("invalid_weather_payload")
            log_event("invalid_weather_payload", level="warning", provider=provider.name, kind=exc.kind)
        log_event("weather_provider_failure", level="warning", provider=provider.name, kind=exc.kind,
                  upstream_status=exc.upstream_status, latency_ms=latency, days=days)
        with _lock:
            _recent_failures[key] = (time.monotonic(), exc)
            _status.update(last_failure_at=_utc_stamp(), last_failure_kind=exc.kind)
        if fallback_policy() == "error":
            raise WeatherUnavailableError(exc) from exc
        return _fallback(latitude, longitude, days, exc)
    except Exception as exc:                                  # a provider bug must not leak as a 500 or fake weather
        wrapped = ProviderError(f"{type(exc).__name__}: {exc}"[:200], kind="provider_error")
        count("weather_provider_failure")
        log_event("weather_provider_failure", level="error", provider=provider.name, kind="provider_error", exc_type=type(exc).__name__)
        with _lock:
            _recent_failures[key] = (time.monotonic(), wrapped)
            _status.update(last_failure_at=_utc_stamp(), last_failure_kind="provider_error")
        if fallback_policy() == "error":
            raise WeatherUnavailableError(wrapped) from exc
        return _fallback(latitude, longitude, days, wrapped)

    count("weather_provider_success")
    log_event("weather_provider_success", provider=provider.name, latency_ms=round((time.monotonic() - t0) * 1000),
              days_returned=len(forecast.daily), partial=forecast.partial,
              date_from=str(forecast.daily[0].date), date_to=str(forecast.daily[-1].date))
    with _lock:
        _recent_failures.pop(key, None)
        _status.update(last_success_at=_utc_stamp())
        if ttl:
            _cache[key] = (time.monotonic(), forecast)
            _cache.move_to_end(key)
            while len(_cache) > _MAX_CACHE_ENTRIES:
                _cache.popitem(last=False)
    return forecast
