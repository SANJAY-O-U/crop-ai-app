"""Weather provider normalization — no live network calls, deterministic."""

from app.weather.providers.mock import MockWeatherProvider
from app.weather.providers.open_meteo import OpenMeteoProvider

_FAKE_OPEN_METEO_RESPONSE = {
    "latitude": 13.39,
    "longitude": 77.74,
    "elevation": 929.0,
    "daily": {
        "time": ["2026-01-01", "2026-01-02"],
        "temperature_2m_max": [30.0, 31.5],
        "temperature_2m_min": [18.0, 19.0],
        "precipitation_sum": [12.0, 0.0],
        "windspeed_10m_max": [10.0, 14.0],
        "relative_humidity_2m_mean": [70, 65],
    },
}


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_open_meteo_provider_normalizes_response(monkeypatch):
    def fake_get(url, params, timeout):
        return _FakeResponse(_FAKE_OPEN_METEO_RESPONSE)

    monkeypatch.setattr("app.weather.providers.open_meteo.httpx.get", fake_get)

    forecast = OpenMeteoProvider().get_forecast(13.40, 77.73, days=2)

    assert forecast.source == "open-meteo"
    assert forecast.is_mocked is False
    assert forecast.elevation_m == 929.0
    assert len(forecast.daily) == 2

    day0 = forecast.daily[0]
    assert str(day0.date) == "2026-01-01"
    assert day0.temperature_max_c == 30.0
    assert day0.temperature_min_c == 18.0
    assert day0.rainfall_mm == 12.0
    assert day0.humidity_pct == 70
    assert day0.wind_kmph == 10.0


def test_open_meteo_provider_propagates_failure(monkeypatch):
    def fake_get(url, params, timeout):
        raise ConnectionError("no network")

    monkeypatch.setattr("app.weather.providers.open_meteo.httpx.get", fake_get)

    try:
        OpenMeteoProvider().get_forecast(13.40, 77.73, days=2)
        assert False, "expected an exception to propagate"
    except ConnectionError:
        pass


def test_mock_provider_shape_and_labeling():
    forecast = MockWeatherProvider().get_forecast(13.40, 77.73, days=5)

    assert forecast.source == "mock"
    assert forecast.is_mocked is True
    assert forecast.elevation_m is None
    assert len(forecast.daily) == 5
    for day in forecast.daily:
        assert 0 <= day.humidity_pct <= 100
        assert day.rainfall_mm >= 0
        assert day.wind_kmph >= 0


def test_mock_provider_is_deterministic_for_same_point():
    a = MockWeatherProvider().get_forecast(13.40, 77.73, days=3)
    b = MockWeatherProvider().get_forecast(13.40, 77.73, days=3)
    assert [d.rainfall_mm for d in a.daily] == [d.rainfall_mm for d in b.daily]
