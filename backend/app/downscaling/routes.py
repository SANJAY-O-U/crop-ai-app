from fastapi import APIRouter, HTTPException, Query

from app.downscaling.schemas import DownscaledForecast
from app.downscaling.service import (
    UnknownBlockError,
    UnknownPanchayatError,
    get_downscaled_forecast,
    get_downscaled_forecasts_for_block,
)

router = APIRouter()


@router.get("/{panchayat_id}/forecast", response_model=DownscaledForecast)
def downscale_panchayat(panchayat_id: str, days: int = Query(default=7, ge=1, le=16)):
    try:
        return get_downscaled_forecast(panchayat_id, days)
    except UnknownPanchayatError:
        raise HTTPException(status_code=404, detail=f"Panchayat '{panchayat_id}' not found.")
    except UnknownBlockError as exc:
        raise HTTPException(status_code=500, detail=f"Panchayat references unknown block '{exc}'.")


@router.get("/block/{block_id}/forecast", response_model=list[DownscaledForecast])
def downscale_block(block_id: str, days: int = Query(default=7, ge=1, le=16)):
    """All panchayats in a block, downscaled — powers the Weather Map / Dashboard views."""
    try:
        return get_downscaled_forecasts_for_block(block_id, days)
    except UnknownBlockError:
        raise HTTPException(status_code=404, detail=f"Block '{block_id}' not found.")
