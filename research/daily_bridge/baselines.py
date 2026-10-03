"""Baselines A (block-as-is) and B (the PRODUCTION correction, imported -- not re-typed)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from daily_bridge import config

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
from app.downscaling.baseline import apply_baseline  # noqa: E402  (the live Phase 1 function)
from app.weather.schemas import DailyWeather, PointForecast  # noqa: E402


def block_as_is(block_daily: pd.DataFrame) -> pd.DataFrame:
    """Baseline A: the block value is the Panchayat value (what the API would return with no correction)."""
    return block_daily.copy()


def production_baseline(block_daily: pd.DataFrame, block_elevation_m: float, panchayat_elevation_m: float) -> pd.DataFrame:
    """Baseline B: backend/app/downscaling/baseline.py::apply_baseline, run on the block daily values.
    Only days where all five block values are valid are passed (the live schema rejects NaN)."""
    ok = block_daily.dropna(subset=config.DAILY_VARIABLES).reset_index(drop=True)
    daily = [DailyWeather(date=r[config.DAY_COLUMN], temperature_min_c=r["temperature_min_c"],
                          temperature_max_c=r["temperature_max_c"], rainfall_mm=r["rainfall_mm"],
                          humidity_pct=r["humidity_pct"], wind_kmph=r["wind_kmph"])
             for _, r in ok.iterrows()]
    forecast = PointForecast(latitude=0.0, longitude=0.0, source="offline-evaluation", daily=daily)
    adjusted = apply_baseline(forecast, block_elevation_m, panchayat_elevation_m)
    out = pd.DataFrame([a.model_dump() for a in adjusted]).rename(columns={"date": config.DAY_COLUMN})
    out[config.DAY_COLUMN] = out[config.DAY_COLUMN].astype(str)
    return out


def constant_offset(train_target, train_block, block_test):
    """Diagnostic baseline: block value + one constant (mean train error). Separates plain bias removal from anything a model learns."""
    t, b = np.asarray(train_target, float), np.asarray(train_block, float)
    ok = ~(np.isnan(t) | np.isnan(b))
    return np.asarray(block_test, float) + float((t[ok] - b[ok]).mean())
