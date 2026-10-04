from fastapi import APIRouter, HTTPException, Query

from app.geospatial import service as geo_service
from app.weather.schemas import PointForecast
from app.weather.service import get_point_forecast

router = APIRouter()


@router.get("/block/{block_id}/forecast", response_model=PointForecast)
def get_block_forecast(block_id: str, days: int = Query(default=7, ge=1, le=16)):
    """
    Block-level forecast — the coarse input to the downscaling engine.
    Resolves the block's centroid via the geospatial module, then fetches a
    single forecast for that point (see app/weather/service.py for provider
    selection, caching and fallback behaviour).

    Declared `def` (not `async def`) on purpose: the provider call is blocking I/O, so FastAPI runs it in its
    threadpool instead of stalling the event loop. A provider failure becomes HTTP 502/503 when WEATHER_FALLBACK=error;
    otherwise the response is an explicitly labelled mock fallback (see app/weather/service.py).
    """
    block = geo_service.get_block(block_id)
    if block is None:
        raise HTTPException(status_code=404, detail=f"Block '{block_id}' not found.")

    return get_point_forecast(block.latitude, block.longitude, days)
