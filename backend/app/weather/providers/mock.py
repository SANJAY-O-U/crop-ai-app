"""
Deterministic offline fallback provider.

Used when the live provider (Open-Meteo) is unreachable — e.g. no internet
during a demo — so the app still returns *something* rather than a 502, and
used directly in tests so they don't depend on network access.

The numbers are a fixed, seeded pattern derived from the coordinates — NOT a
weather model of any kind. Every response is marked is_mocked=True and
source="mock" so a caller can never mistake this for real data.
"""

from datetime import date, timedelta

from app.weather.schemas import DailyWeather, PointForecast


class MockWeatherProvider:
    name = "mock"

    def get_forecast(self, latitude: float, longitude: float, days: int) -> PointForecast:
        seed = abs(hash((round(latitude, 3), round(longitude, 3)))) % 1000
        today = date.today()

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

        return PointForecast(
            latitude=latitude,
            longitude=longitude,
            elevation_m=None,
            source=self.name,
            is_mocked=True,
            daily=daily,
        )
