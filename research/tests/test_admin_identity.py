"""
Validates the Stage 1 real Karnataka administrative identity dataset
(research/admin_identity/karnataka_identity.csv). These tests run against
the COMMITTED CSV, not a live network fetch — they check the data that
will actually ship, not the fetch script's behavior in isolation.
"""

import csv

import pytest

from admin_identity.identity_data import (
    IDENTITY_CSV_PATH,
    REQUIRED_FIELDS,
    get_block_summary,
    load_identity_rows,
)


@pytest.fixture
def rows():
    return load_identity_rows()


def test_dataset_is_nonempty_and_has_required_columns(rows):
    assert len(rows) > 0
    for row in rows:
        for field in REQUIRED_FIELDS:
            assert field in row and row[field], f"missing/empty '{field}' in row {row}"


def test_panchayat_codes_are_unique(rows):
    codes = [r["panchayat_lgd_code"] for r in rows]
    assert len(codes) == len(set(codes)), f"duplicate panchayat_lgd_code values found: {codes}"


def test_panchayat_codes_look_real_not_fabricated(rows):
    # Real LGD Localbody Codes are plain numeric strings, never a
    # placeholder-style identifier like "PANCH-DEMO-001".
    for r in rows:
        code = r["panchayat_lgd_code"]
        assert code.isdigit(), f"panchayat_lgd_code '{code}' does not look like a real LGD numeric code"
        assert "DEMO" not in r["panchayat_name"].upper()
        assert "DEMO" not in code.upper()


def test_every_panchayat_resolves_to_exactly_one_block(rows):
    block_codes = {r["block_lgd_code"] for r in rows}
    block_names = {r["block_name"] for r in rows}
    assert len(block_codes) == 1, f"panchayats span more than one block: {block_codes}"
    assert len(block_names) == 1, f"panchayats span more than one block name: {block_names}"


def test_block_resolves_to_expected_district_and_state(rows):
    summary = get_block_summary(rows)
    assert summary["state_name"] == "Karnataka"
    assert summary["state_lgd_code"] == "29"
    assert summary["district_name"] == "Bagalkot"
    assert summary["district_lgd_code"] == "479"
    assert summary["block_name"] == "Guledagudda"
    assert summary["block_lgd_code"] == "296788"


def test_get_block_summary_raises_if_rows_span_multiple_blocks():
    fabricated_multi_block_rows = [
        {"state_name": "Karnataka", "state_lgd_code": "29",
         "district_name": "Bagalkot", "district_lgd_code": "479",
         "block_name": "Guledagudda", "block_lgd_code": "296788"},
        {"state_name": "Karnataka", "state_lgd_code": "29",
         "district_name": "Bagalkot", "district_lgd_code": "479",
         "block_name": "Badami", "block_lgd_code": "6084"},
    ]
    with pytest.raises(ValueError):
        get_block_summary(fabricated_multi_block_rows)


def test_no_coordinate_or_elevation_columns_present():
    with open(IDENTITY_CSV_PATH, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    forbidden_substrings = ["lat", "lon", "elevation", "coord", "geometry", "centroid"]
    for column in header:
        lowered = column.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"unexpected spatial column '{column}' in identity CSV"


def test_source_provenance_preserved_on_every_row(rows):
    for r in rows:
        assert r["source"].strip() != ""
        assert "lgdirectory.gov.in" in r["source_url"] or "opendata" in r["source_url"]
        assert r["retrieved_at"] == "2026-09-22"
        assert "identity/metadata only" in r["source_note"]
        assert "pilot_points.py" in r["source_note"]  # explicitly disclaims spatial linkage


def test_source_note_discloses_the_district_code_namespace_ambiguity(rows):
    for r in rows:
        assert "Revenue-Department district code" in r["source_note"]


def test_load_identity_rows_raises_on_missing_field(tmp_path):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text(
        "state_name,state_lgd_code,district_name,district_lgd_code,block_name,"
        "block_lgd_code,panchayat_name,panchayat_lgd_code,source,source_url,"
        "retrieved_at,source_note\n"
        "Karnataka,29,Bagalkot,479,Guledagudda,296788,,215153,src,url,2026-09-22,note\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_identity_rows(bad_csv)


def test_load_identity_rows_raises_on_empty_file(tmp_path):
    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text(
        "state_name,state_lgd_code,district_name,district_lgd_code,block_name,"
        "block_lgd_code,panchayat_name,panchayat_lgd_code,source,source_url,"
        "retrieved_at,source_note\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_identity_rows(empty_csv)
