"""
Deterministic offline provider.

Used (a) in tests, (b) when WEATHER_PROVIDER=mock, and (c) as an EXPLICIT, labelled fallback when the live provider
fails and WEATHER_FALLBACK=mock (the default; set WEATHER_FALLBACK=error to disable it).

The numbers are a fixed, seeded pattern derived from the coordinates — NOT a
weather model of any kind. Every response is marked is_mocked=True,
source="mock" and a data_origin of "mock_configured" or "mock_fallback", so a caller can never mistake this for real
data. Dates follow the same local-calendar-day definition as the live provider (Asia/Kolkata, UTC+05:30).
"""

from datetime import datetime, timedelta, timezone

from app.weather.schemas import DailyWeather, PointForecast

IST = timezone(timedelta(hours=5, minutes=30))


class MockWeatherProvider:
    name = "mock"

    def get_forecast(self, latitude: float, longitude: float, days: int) -> PointForecast:
        seed = abs(hash((round(latitude, 3), round(longitude, 3)))) % 1000
        now = datetime.now(timezone.utc)
        today = now.astimezone(IST).date()            # the local day, not the server's UTC/local day

        daily = []
        for i in range(days):
            wobble = (seed + i * 7) % 20  # 0-19, just for day-to-day variation
            daily.append(DailyWeather(
                date=today + timedelta(days=i),
                temperature_min_c=18.0 + wobble * 0.2,
                temperature_max_c=28.0 + wobble * 0.3,
                rainfall_mm=float((seed + i * 13) % 60),
                humidity_pct=55.0 + wobble,
                wind_kmph=8.0 + wobble * 0.5,
            ))

        stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        return PointForecast(
            latitude=latitude,
            longitude=longitude,
            elevation_m=None,
            source=self.name,
            is_mocked=True,
            data_origin="mock_configured",
            retrieved_at=stamp,
            forecast_generated_at=stamp,
            timezone="Asia/Kolkata",
            utc_offset_seconds=19800,
            requested_days=days,
            forecast_horizon_days=len(daily),
            daily=daily,
        )
