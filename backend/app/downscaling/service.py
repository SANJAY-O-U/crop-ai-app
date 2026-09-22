"""
Orchestrates block -> panchayat downscaling:
  1. resolve panchayat and its parent block (geospatial module)
  2. fetch ONE block-level forecast (weather module)
  3. apply the baseline elevation-aware adjustment (downscaling.baseline)

Phase 2 will add an ML-corrected method here behind the same function
signature — callers won't need to change; only the "method" field on the
response will start saying "ml_corrected" once that exists.
"""

from app.downscaling.baseline import apply_baseline, build_adjustment_metadata
from app.downscaling.schemas import DownscaledForecast
from app.geospatial import service as geo_service
from app.geospatial.schemas import Block, Panchayat
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
    # Prefer the elevation the live provider returned for the block point (if
    # any); fall back to the seed data's own elevation_m otherwise.
    block_elevation = block_forecast.elevation_m or block.elevation_m
    panchayat_elevation = panchayat.elevation_m

    daily = apply_baseline(block_forecast, block_elevation, panchayat_elevation)
    adjustment = build_adjustment_metadata(block_elevation, panchayat_elevation)

    return DownscaledForecast(
        panchayat_id=panchayat.panchayat_id,
        panchayat_name=panchayat.panchayat_name,
        block_id=block.block_id,
        block_name=block.block_name,
        method="baseline",
        block_source=block_forecast,
        adjustment=adjustment,
        daily=daily,
    )


def get_downscaled_forecast(panchayat_id: str, days: int) -> DownscaledForecast:
    panchayat, block = _resolve(panchayat_id)
    block_forecast = get_point_forecast(block.latitude, block.longitude, days)
    return _downscale(panchayat, block, block_forecast)


def get_downscaled_forecasts_for_block(block_id: str, days: int) -> list[DownscaledForecast]:
    block = geo_service.get_block(block_id)
    if block is None:
        raise UnknownBlockError(block_id)

    panchayats = geo_service.list_panchayats(block_id)
    # Fetch the block forecast ONCE and reuse it for every panchayat in the
    # block, rather than re-fetching the same point per panchayat.
    block_forecast = get_point_forecast(block.latitude, block.longitude, days)

    return [_downscale(p, block, block_forecast) for p in panchayats]
