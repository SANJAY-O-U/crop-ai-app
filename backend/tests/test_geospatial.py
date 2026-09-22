from app.geospatial import service


def test_list_blocks_returns_seeded_pilot_block():
    blocks = service.list_blocks()
    assert len(blocks) == 1
    assert blocks[0].block_id == "BLOCK-DEMO-001"
    assert blocks[0].is_demo_data is True


def test_get_block_known_id():
    block = service.get_block("BLOCK-DEMO-001")
    assert block is not None
    assert block.block_name == "Demo Block"


def test_get_block_unknown_id_returns_none():
    assert service.get_block("DOES-NOT-EXIST") is None


def test_list_panchayats_for_block():
    panchayats = service.list_panchayats("BLOCK-DEMO-001")
    assert len(panchayats) == 3
    ids = {p.panchayat_id for p in panchayats}
    assert ids == {"PANCH-DEMO-001", "PANCH-DEMO-002", "PANCH-DEMO-003"}
    assert all(p.is_demo_data for p in panchayats)


def test_list_panchayats_unknown_block_returns_empty():
    assert service.list_panchayats("DOES-NOT-EXIST") == []


def test_get_panchayat_unknown_id_returns_none():
    assert service.get_panchayat("DOES-NOT-EXIST") is None
