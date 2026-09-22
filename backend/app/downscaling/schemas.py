from typing import Literal

from pydantic import BaseModel

from app.weather.schemas import DailyWeather, PointForecast

DownscalingMethod = Literal["baseline", "ml_corrected"]


class DownscaledForecast(BaseModel):
    panchayat_id: str
    panchayat_name: str
    block_id: str
    block_name: str
    method: DownscalingMethod
    block_source: PointForecast
    adjustment: dict
    daily: list[DailyWeather]
