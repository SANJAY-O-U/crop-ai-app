"""
Lookup functions over the seed data. Deliberately in-memory / no database —
Phase 1 has exactly one pilot block, so a DB would be pure overhead
(see architecture doc, Section I / Section 7 of this phase's instructions).
"""

from app.geospatial.schemas import Block, Panchayat
from app.geospatial.seed_data import DEMO_BLOCK, DEMO_PANCHAYATS

_BLOCKS_BY_ID: dict[str, Block] = {DEMO_BLOCK.block_id: DEMO_BLOCK}
_PANCHAYATS_BY_ID: dict[str, Panchayat] = {p.panchayat_id: p for p in DEMO_PANCHAYATS}


def get_block(block_id: str) -> Block | None:
    return _BLOCKS_BY_ID.get(block_id)


def list_blocks() -> list[Block]:
    return list(_BLOCKS_BY_ID.values())


def get_panchayat(panchayat_id: str) -> Panchayat | None:
    return _PANCHAYATS_BY_ID.get(panchayat_id)


def list_panchayats(block_id: str | None = None) -> list[Panchayat]:
    values = list(_PANCHAYATS_BY_ID.values())
    if block_id is None:
        return values
    return [p for p in values if p.block_id == block_id]
