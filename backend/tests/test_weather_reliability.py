"""Open-Meteo provider hardening and the weather service's failure/fallback/cache behaviour. No network."""

from datetime import date

import httpx
import pytest
from pydantic import ValidationError

from app.weather import service as weather_service
from app.weather.errors import ProviderError, WeatherUnavailableError
from app.weather.providers import open_meteo
from app.weather.providers.open_meteo import OpenMeteoProvider
from app.weather.schemas import DailyWeather, PointForecast
from cc_helpers import FakeResponse, StubProvider, live_forecast, open_meteo_body, provider_error


def provider():
    return OpenMeteoProvider(retries=1, backoff_s=0.0)


def patch_get(monkeypatch, *outcomes):
    """Each call returns/raises the next outcome (the last one repeats). Returns the call log."""
    calls = []

    def fake_get(url, params, timeout):
        calls.append({"url": url, "params": params, "timeout": timeout})
        o = outcomes[min(len(calls) - 1, len(outcomes) - 1)]
        if isinstance(o, Exception):
            raise o
        return o

    monkeypatch.setattr(open_meteo.httpx, "get", fake_get)
    return calls


# ── 1. success + provenance ────────────────────────────────────────────────────────────────────────────
def test_success_normalizes_and_records_provenance(monkeypatch):
    calls = patch_get(monkeypatch, FakeResponse(open_meteo_body(n=3)))
    f = provider().get_forecast(13.4, 77.73, 3)
    assert f.source == "open-meteo" and f.is_mocked is False and f.data_origin == "live_provider" and f.fallback_reason is None
    assert f.timezone == "Asia/Kolkata" and f.utc_offset_seconds == 19800
    assert f.retrieved_at.endswith("Z") and f.forecast_generated_at is None      # the provider does not expose model-run time
    assert f.requested_days == 3 and f.forecast_horizon_days == 3 and f.partial is False and f.omitted_dates == []
    assert len(calls) == 1 and calls[0]["params"]["timezone"] == "auto"
    assert calls[0]["timeout"].read == 8.0 and calls[0]["timeout"].connect == 3.0       # bounded timeouts


def test_provider_dates_are_local_dates_passed_through_unchanged(monkeypatch):
    # 2026-10-05 is the LOCAL (IST) day label from the provider; no UTC shifting may move it to the 4th or 6th.
    patch_get(monkeypatch, FakeResponse(open_meteo_body(n=2, first="2026-10-05", offset=19800)))
    f = provider().get_forecast(13.4, 77.73, 2)
    assert [d.date for d in f.daily] == [date(2026, 10, 5), date(2026, 10, 6)]


# ── 2-3. timeout / connection / HTTP failures ─────────────────────────────────────────────────────────
def test_read_timeout_is_typed_and_not_retried(monkeypatch):
    calls = patch_get(monkeypatch, httpx.ReadTimeout("slow"))
    with pytest.raises(ProviderError) as ei:
        provider().get_forecast(13.4, 77.73, 3)
    assert ei.value.kind == "timeout" and isinstance(ei.value, TimeoutError) and len(calls) == 1      # no doubling of the wait


def test_connect_timeout_is_retried_once_at_most(monkeypatch):
    calls = patch_get(monkeypatch, httpx.ConnectTimeout("no route"))
    with pytest.raises(ProviderError) as ei:
        provider().get_forecast(13.4, 77.73, 3)
    assert ei.value.kind == "timeout" and len(calls) == 2


def test_connection_failure_is_typed_and_builtin_compatible(monkeypatch):
    patch_get(monkeypatch, httpx.ConnectError("down"))
    with pytest.raises(ProviderError) as ei:
        provider().get_forecast(13.4, 77.73, 3)
    assert ei.value.kind == "connection" and isinstance(ei.value, ConnectionError)


def test_http_5xx_is_retried_once_then_reported_with_status(monkeypatch):
    calls = patch_get(monkeypatch, FakeResponse(status=503))
    with pytest.raises(ProviderError) as ei:
        provider().get_forecast(13.4, 77.73, 3)
    assert ei.value.kind == "http_error" and ei.value.upstream_status == 503 and len(calls) == 2


def test_http_4xx_is_not_retried(monkeypatch):
    calls = patch_get(monkeypatch, FakeResponse(status=400))
    with pytest.raises(ProviderError) as ei:
        provider().get_forecast(13.4, 77.73, 3)
    assert ei.value.kind == "http_error" and ei.value.upstream_status == 400 and len(calls) == 1


def test_retry_that_succeeds_returns_real_data(monkeypatch):
    calls = patch_get(monkeypatch, httpx.ConnectTimeout("slow"), FakeResponse(open_meteo_body(n=2)))
    assert provider().get_forecast(13.4, 77.73, 2).is_mocked is False and len(calls) == 2


# ── 4. malformed responses ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("response,kind", [
    (FakeResponse(json_error=True), "malformed_response"),
    (FakeResponse([1, 2, 3]), "malformed_response"),
    (FakeResponse({"latitude": 1}), "malformed_response"),
    (FakeResponse({"daily": {"time": ["2026-10-05"]}}), "malformed_response"),
])
def test_malformed_shapes_are_rejected(monkeypatch, response, kind):
    patch_get(monkeypatch, response)
    with pytest.raises(ProviderError) as ei:
        provider().get_forecast(13.4, 77.73, 3)
    assert ei.value.kind == kind


def test_inconsistent_array_lengths_are_rejected(monkeypatch):
    body = open_meteo_body(n=3)
    body["daily"]["precipitation_sum"] = body["daily"]["precipitation_sum"][:2]
    patch_get(monkeypatch, FakeResponse(body))
    with pytest.raises(ProviderError) as ei:
        provider().get_forecast(13.4, 77.73, 3)
    assert ei.value.kind == "malformed_response"


def test_invalid_duplicate_or_unsorted_dates_are_rejected(monkeypatch):
    for times in (["2026-10-05", "2026-10-05", "2026-10-06"], ["2026-10-06", "2026-10-05", "2026-10-07"], ["2026-10-05", "not-a-date", "2026-10-07"]):
        body = open_meteo_body(n=3)
        body["daily"]["time"] = times
        patch_get(monkeypatch, FakeResponse(body))
        with pytest.raises(ProviderError) as ei:
            provider().get_forecast(13.4, 77.73, 3)
        assert ei.value.kind == "malformed_response"


def test_non_numeric_value_is_rejected(monkeypatch):
    body = open_meteo_body(n=2)
    body["daily"]["temperature_2m_max"][0] = "hot"
    patch_get(monkeypatch, FakeResponse(body))
    with pytest.raises(ProviderError):
        provider().get_forecast(13.4, 77.73, 2)


# ── 5-6. null values, partial forecast ───────────────────────────────────────────────────────────────
def test_null_day_is_omitted_not_filled_and_marked_partial(monkeypatch):
    patch_get(monkeypatch, FakeResponse(open_meteo_body(n=4, nulls=(3,))))
    f = provider().get_forecast(13.4, 77.73, 4)
    assert len(f.daily) == 3 and f.omitted_dates == ["2026-10-08"] and f.partial is True and f.forecast_horizon_days == 3
    assert f.requested_days == 4 and f.is_mocked is False


def test_provider_returning_fewer_days_than_requested_is_partial(monkeypatch):
    patch_get(monkeypatch, FakeResponse(open_meteo_body(n=2)))
    f = provider().get_forecast(13.4, 77.73, 5)
    assert f.partial is True and f.omitted_dates == [] and len(f.daily) == 2


def test_all_null_forecast_is_an_error_not_an_empty_success(monkeypatch):
    patch_get(monkeypatch, FakeResponse(open_meteo_body(n=2, nulls=(0, 1))))
    with pytest.raises(ProviderError) as ei:
        provider().get_forecast(13.4, 77.73, 2)
    assert ei.value.kind == "empty_forecast"


# ── 9. invalid weather values, units ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("field,value", [("temperature_2m_max", 999.0), ("precipitation_sum", -5.0), ("relative_humidity_2m_mean", 130.0),
                                         ("windspeed_10m_max", -3.0), ("windspeed_10m_max", 9999.0)])
def test_out_of_bounds_values_reject_the_response(monkeypatch, field, value):
    body = open_meteo_body(n=2)
    body["daily"][field][0] = value
    patch_get(monkeypatch, FakeResponse(body))
    with pytest.raises(ProviderError) as ei:
        provider().get_forecast(13.4, 77.73, 2)
    assert ei.value.kind == "invalid_payload"


def test_min_above_max_rejects_the_response(monkeypatch):
    body = open_meteo_body(n=2)
    body["daily"]["temperature_2m_min"][0], body["daily"]["temperature_2m_max"][0] = 35.0, 25.0
    patch_get(monkeypatch, FakeResponse(body))
    with pytest.raises(ProviderError) as ei:
        provider().get_forecast(13.4, 77.73, 2)
    assert ei.value.kind == "invalid_payload"


def test_unexpected_units_are_rejected(monkeypatch):
    body = open_meteo_body(n=2)
    body["daily_units"]["windspeed_10m_max"] = "mp/h"
    patch_get(monkeypatch, FakeResponse(body))
    with pytest.raises(ProviderError) as ei:
        provider().get_forecast(13.4, 77.73, 2)
    assert ei.value.kind == "unexpected_units"


def test_extreme_legitimate_values_are_accepted(monkeypatch):
    body = open_meteo_body(n=1)
    body["daily"]["precipitation_sum"][0] = 900.0
    body["daily"]["temperature_2m_max"][0] = 49.0
    patch_get(monkeypatch, FakeResponse(body))
    assert provider().get_forecast(13.4, 77.73, 1).daily[0].rainfall_mm == 900.0


def test_absurd_elevation_becomes_unknown_not_an_error(monkeypatch):
    patch_get(monkeypatch, FakeResponse(open_meteo_body(n=1, elevation=123456.0)))
    assert provider().get_forecast(13.4, 77.73, 1).elevation_m is None


def test_schema_validators():
    d = dict(date=date(2026, 1, 1), temperature_min_c=20, temperature_max_c=30, rainfall_mm=1, humidity_pct=50, wind_kmph=5)
    DailyWeather(**d)
    for bad in ({"humidity_pct": 101}, {"rainfall_mm": -0.1}, {"wind_kmph": -1}, {"temperature_min_c": 31}, {"temperature_max_c": float("nan")}):
        with pytest.raises(ValidationError):
            DailyWeather(**{**d, **bad})
    day = DailyWeather(**d)
    with pytest.raises(ValidationError):
        PointForecast(latitude=95, longitude=0, source="x", daily=[day])
    with pytest.raises(ValidationError):
        PointForecast(latitude=0, longitude=0, source="x", daily=[day, day])           # duplicate dates


# ── 7-8. service: fallback, provenance, cache, cooldown ────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for v in ("WEATHER_PROVIDER", "WEATHER_FALLBACK", "WEATHER_CACHE_TTL_S", "WEATHER_FAILURE_COOLDOWN_S"):
        monkeypatch.delenv(v, raising=False)
    weather_service.clear_state()
    from app import observability
    observability.reset_counters()
    yield
    weather_service.clear_state()


def use(monkeypatch, stub):
    monkeypatch.setitem(weather_service._PROVIDERS, "open-meteo", stub)
    return stub


def test_service_returns_live_forecast_unchanged(monkeypatch):
    stub = use(monkeypatch, StubProvider(result=live_forecast(n=3)))
    f = weather_service.get_point_forecast(13.4, 77.73, 3)
    assert f.data_origin == "live_provider" and f.is_mocked is False and f.fallback_reason is None and stub.calls == 1


def test_provider_failure_falls_back_to_an_explicitly_labelled_mock(monkeypatch):
    use(monkeypatch, StubProvider(error=provider_error("timeout", "timed out after 8s")))
    f = weather_service.get_point_forecast(13.4, 77.73, 3)
    assert f.is_mocked is True and f.source == "mock" and f.data_origin == "mock_fallback"
    assert f.fallback_reason.startswith("timeout:") and len(f.daily) == 3


def test_fallback_can_be_disabled_so_failure_is_never_disguised(monkeypatch):
    monkeypatch.setenv("WEATHER_FALLBACK", "error")
    use(monkeypatch, StubProvider(error=provider_error("connection")))
    with pytest.raises(WeatherUnavailableError) as ei:
        weather_service.get_point_forecast(13.4, 77.73, 3)
    assert ei.value.kind == "connection"


def test_unexpected_provider_bug_is_treated_as_failure_not_weather(monkeypatch):
    use(monkeypatch, StubProvider(error=KeyError("oops")))
    f = weather_service.get_point_forecast(13.4, 77.73, 2)
    assert f.data_origin == "mock_fallback" and f.fallback_reason.startswith("provider_error")


def test_configured_mock_is_labelled_mock_configured(monkeypatch):
    monkeypatch.setenv("WEATHER_PROVIDER", "mock")
    f = weather_service.get_point_forecast(13.4, 77.73, 2)
    assert f.is_mocked and f.data_origin == "mock_configured" and f.fallback_reason is None


def test_live_responses_are_cached_with_original_retrieval_time(monkeypatch):
    stub = use(monkeypatch, StubProvider(result=live_forecast(n=3)))
    first = weather_service.get_point_forecast(13.4, 77.73, 3)
    second = weather_service.get_point_forecast(13.4, 77.73, 3)
    assert stub.calls == 1 and first.from_cache is False
    assert second.from_cache is True and second.cache_age_s is not None and second.retrieved_at == first.retrieved_at
    assert weather_service.get_point_forecast(13.4, 77.73, 5).from_cache is False and stub.calls == 2     # different days -> different key


def test_cache_can_be_disabled(monkeypatch):
    monkeypatch.setenv("WEATHER_CACHE_TTL_S", "0")
    stub = use(monkeypatch, StubProvider(result=live_forecast(n=3)))
    weather_service.get_point_forecast(13.4, 77.73, 3)
    weather_service.get_point_forecast(13.4, 77.73, 3)
    assert stub.calls == 2


def test_mock_fallback_is_never_cached_and_failures_enter_a_cooldown(monkeypatch):
    stub = use(monkeypatch, StubProvider(error=provider_error("timeout")))
    a = weather_service.get_point_forecast(13.4, 77.73, 3)
    b = weather_service.get_point_forecast(13.4, 77.73, 3)            # inside the cooldown: provider is not hit again
    assert stub.calls == 1 and a.data_origin == b.data_origin == "mock_fallback" and "cooldown" in b.fallback_reason
    monkeypatch.setenv("WEATHER_FAILURE_COOLDOWN_S", "0")
    weather_service.get_point_forecast(13.4, 77.73, 3)
    assert stub.calls == 2


def test_recovery_after_failure_returns_live_data_again(monkeypatch):
    monkeypatch.setenv("WEATHER_FAILURE_COOLDOWN_S", "0")
    stub = use(monkeypatch, StubProvider(error=provider_error("timeout")))
    assert weather_service.get_point_forecast(13.4, 77.73, 3).is_mocked is True
    stub.error = None
    assert weather_service.get_point_forecast(13.4, 77.73, 3).is_mocked is False
