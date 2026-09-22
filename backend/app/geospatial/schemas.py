from pydantic import BaseModel


class Block(BaseModel):
    block_id: str
    block_name: str
    district: str
    state: str
    latitude: float
    longitude: float
    elevation_m: float | None = None
    is_demo_data: bool = True


class Panchayat(BaseModel):
    panchayat_id: str
    panchayat_name: str
    block_id: str
    block_name: str
    district: str
    state: str
    latitude: float
    longitude: float
    elevation_m: float | None = None
    is_demo_data: bool = True
