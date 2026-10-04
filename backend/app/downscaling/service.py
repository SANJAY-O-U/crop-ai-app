"""
Orchestrates block -> panchayat downscaling:
  1. resolve panchayat and its parent block (geospatial module)
  2. fetch ONE block-level forecast (weather module)
  3. apply the active correction strategy (downscaling.strategy) -- today always the deterministic baseline

Outcomes are distinguishable and never disguised:
  * weather unavailable        -> the weather service raises (HTTP 502/503) or returns an explicitly labelled mock
  * weather ok, elevation bad  -> block values are returned unchanged, provenance.correction_status says why
  * weather ok, elevation ok   -> baseline applied (correction_status = "applied")
"""

from collections import Counter

from app.downscaling.schemas import DownscaledForecast, Provenance
from app.downscaling.strategy import active_strategy, strategy_status
from app.geospatial import service as geo_service
from app.geospatial.schemas import Block, Panchayat
from app.observability import count, log_event
from app.weather.service import get_point_forecast


class UnknownPanchayatError(Exception):
    pass


class UnknownBlockError(Exception):
    pass


def _resolve(panchayat_id: str) -> tuple[Panchayat, Block]:
    panchayat = geo_service.get_panchayat(panchayat_id)
    if panchayat is None:
        raise UnknownPanchayatError(panchayat_id)

    block = geo_service.get_block(panchayat.block_id)
    if block is None:
        raise UnknownBlockError(panchayat.block_id)

    return panchayat, block


def _downscale(panchayat: Panchayat, block: Block, block_forecast) -> DownscaledForecast:
    # Prefer the elevation the live provider returned for the block point; use the seed's own elevation_m only when the
    # provider gave none. (`is None`, not `or`: 0 m is a legitimate sea-level elevation.)
    block_elevation = block_forecast.elevation_m if block_forecast.elevation_m is not None else block.elevation_m
    panchayat_elevation = panchayat.elevation_m

    strategy = active_strategy()
    result = strategy.correct(block_forecast, block_elevation, panchayat_elevation)

    provenance = Provenance(
        weather_source=block_forecast.source, data_origin=block_forecast.data_origin, is_mocked=block_forecast.is_mocked,
        fallback_used=block_forecast.data_origin == "mock_fallback", fallback_reason=block_forecast.fallback_reason,
        retrieved_at=block_forecast.retrieved_at, from_cache=block_forecast.from_cache, timezone=block_forecast.timezone,
        forecast_horizon_days=block_forecast.forecast_horizon_days, partial=block_forecast.partial,
        omitted_dates=block_forecast.omitted_dates, correction_method=result.method, correction_status=result.status,
        model_version=result.model_version, block_elevation_m=block_elevation, panchayat_elevation_m=panchayat_elevation,
        elevation_available=result.status == "applied", ml_correction_enabled=strategy_status()["ml_correction_enabled"],
    )
    return DownscaledForecast(
        panchayat_id=panchayat.panchayat_id,
        panchayat_name=panchayat.panchayat_name,
        block_id=block.block_id,
        block_name=block.block_name,
        method=result.method,
        model_version=result.model_version,
        block_source=block_forecast,
        adjustment=result.adjustment,
        daily=result.daily,
        provenance=provenance,
    )


def _log(block_id: str, forecasts: list[DownscaledForecast]) -> None:
    count("downscaling_baseline_used")
    first = forecasts[0] if forecasts else None
    log_event("downscaling_baseline_used", block_id=block_id, panchayats=len(forecasts),
              method=first.method if first else None,
              statuses=dict(Counter(f.provenance.correction_status for f in forecasts)),
              data_origin=first.provenance.data_origin if first else None,
              date_from=str(first.daily[0].date) if first and first.daily else None,
              date_to=str(first.daily[-1].date) if first and first.daily else None)


def get_downscaled_forecast(panchayat_id: str, days: int) -> DownscaledForecast:
    panchayat, block = _resolve(panchayat_id)
    block_forecast = get_point_forecast(block.latitude, block.longitude, days)
    result = _downscale(panchayat, block, block_forecast)
    _log(block.block_id, [result])
    return result


def get_downscaled_forecasts_for_block(block_id: str, days: int) -> list[DownscaledForecast]:
    block = geo_service.get_block(block_id)
    if block is None:
        raise UnknownBlockError(block_id)

    panchayats = geo_service.list_panchayats(block_id)
    # Fetch the block forecast ONCE and reuse it for every panchayat in the
    # block, rather than re-fetching the same point per panchayat.
    block_forecast = get_point_forecast(block.latitude, block.longitude, days)

    results = [_downscale(p, block, block_forecast) for p in panchayats]
    _log(block_id, results)
    return results
