from fastapi import APIRouter, HTTPException, Query

from app.geospatial import service
from app.geospatial.schemas import Block, Panchayat

router = APIRouter()


@router.get("/blocks", response_model=list[Block])
async def get_blocks():
    return service.list_blocks()


@router.get("/blocks/{block_id}", response_model=Block)
async def get_block(block_id: str):
    block = service.get_block(block_id)
    if block is None:
        raise HTTPException(status_code=404, detail=f"Block '{block_id}' not found.")
    return block


@router.get("/panchayats", response_model=list[Panchayat])
async def get_panchayats(block_id: str | None = Query(default=None)):
    return service.list_panchayats(block_id)


@router.get("/panchayats/{panchayat_id}", response_model=Panchayat)
async def get_panchayat(panchayat_id: str):
    panchayat = service.get_panchayat(panchayat_id)
    if panchayat is None:
        raise HTTPException(status_code=404, detail=f"Panchayat '{panchayat_id}' not found.")
    return panchayat
