"""Focused tests for the prospective Open-Meteo forecast archive (no network; fake HTTP client)."""

import hashlib
import json
import stat
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from forecast_archive import collector, flatten, locations, pairing, readiness, reference, schema

T0 = datetime(2026, 10, 4, 20, 0, 0, tzinfo=timezone.utc)      # 2026-10-05 01:30 IST: UTC date != IST date


class FakeResp:
    def __init__(self, body: bytes, status=200):
        self.content, self.status_code = body, status


def make_body(first_day="2026-10-05", n=16, tmin0=20.0, offset=19800, missing_idx=None) -> bytes:
    start = pd.Timestamp(first_day)
    days = [(start + pd.Timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]
    doc = {"latitude": 13.4, "longitude": 77.75, "elevation": 930.0, "generationtime_ms": 0.5, "utc_offset_seconds": offset,
           "timezone": "Asia/Kolkata", "timezone_abbreviation": "GMT+5:30", "daily_units": {"temperature_2m_min": "°C"},
           "daily": {"time": days, "temperature_2m_min": [tmin0 + i for i in range(n)], "temperature_2m_max": [30.0 + i for i in range(n)],
                     "precipitation_sum": [0.0] * n, "relative_humidity_2m_mean": [70.0] * n, "windspeed_10m_max": [10.0] * n}}
    if missing_idx is not None:
        doc["daily"]["temperature_2m_min"][missing_idx] = None
    return json.dumps(doc).encode()


@pytest.fixture
def registry():
    return {"locations": [
        {"location_id": "B1", "location_set": "s", "role": "block", "block_id": "B1", "panchayat_id": None, "latitude": 13.4, "longitude": 77.75,
         "elevation_m": 930.0, "is_demo_data": True, "era5_land_cell": "E5L_13.40N_77.80E"},
        {"location_id": "P1", "location_set": "s", "role": "panchayat", "block_id": "B1", "panchayat_id": "P1", "latitude": 13.37, "longitude": 77.68,
         "elevation_m": 1430.0, "is_demo_data": True, "era5_land_cell": "E5L_13.40N_77.70E"},
        {"location_id": "B2", "location_set": "s", "role": "block", "block_id": "B2", "panchayat_id": None, "latitude": 12.0, "longitude": 77.0,
         "elevation_m": 700.0, "is_demo_data": False, "era5_land_cell": "E5L_12.00N_77.00E"}]}


def run(tmp_path, registry, http, now=T0, **kw):
    return collector.collect(tmp_path, registry=registry, http_get=http, now_fn=lambda: now, **kw)


# ---- schema / provenance / hashing ---------------------------------------------------------------------
def test_archive_record_has_full_schema_and_provenance(tmp_path, registry):
    body = make_body()
    counts = run(tmp_path, registry, lambda u, p, t: FakeResp(body))
    assert counts["stored"] == 2
    rec = collector.read_jsonl(tmp_path / "index.jsonl")[0]
    assert set(rec) == set(schema.INDEX_FIELDS)
    assert rec["provider"] == "open-meteo" and rec["is_mock"] is False and rec["role"] == "block_input"
    assert rec["request_url"] == collector.FORECAST_URL and rec["request_params"]["timezone"] == "auto"
    assert rec["request_params"]["forecast_days"] == schema.FORECAST_DAYS
    assert rec["retrieved_utc"] == "2026-10-04T20:00:00Z" and rec["slot_start_utc"] == "2026-10-04T12:00:00Z"
    assert set(rec["response_meta"]) == set(schema.RESPONSE_META_FIELDS)
    assert rec["response_meta"]["utc_offset_seconds"] == 19800 and rec["response_meta"]["elevation"] == 930.0


def test_raw_response_is_stored_verbatim_hashed_and_read_only(tmp_path, registry):
    body = make_body()
    run(tmp_path, registry, lambda u, p, t: FakeResp(body))
    rec = collector.read_jsonl(tmp_path / "index.jsonl")[0]
    path = tmp_path / rec["raw_path"]
    assert path.read_bytes() == body                                        # exact bytes, not re-serialised
    assert rec["raw_sha256"] == hashlib.sha256(body).hexdigest() and rec["raw_bytes"] == len(body)
    assert not (path.stat().st_mode & stat.S_IWRITE)                         # read-only
    with pytest.raises(FileExistsError):
        open(path, "xb")                                                     # exclusive-create semantics: never overwritten


def test_tampered_raw_file_is_detected_when_flattening(tmp_path, registry):
    run(tmp_path, registry, lambda u, p, t: FakeResp(make_body()))
    rec = collector.read_jsonl(tmp_path / "index.jsonl")[0]
    p = tmp_path / rec["raw_path"]
    p.chmod(stat.S_IWRITE | stat.S_IREAD)
    p.write_bytes(make_body(tmin0=99.0))
    with pytest.raises(ValueError, match="hash mismatch"):
        flatten.flatten(tmp_path)


# ---- duplicate prevention / resumable ------------------------------------------------------------------
def test_second_pass_in_same_slot_makes_no_requests_and_no_duplicates(tmp_path, registry):
    calls = []
    http = lambda u, p, t: (calls.append(p), FakeResp(make_body()))[1]
    run(tmp_path, registry, http)
    n = len(calls)
    counts = run(tmp_path, registry, http, now=T0.replace(hour=22))           # same 12-h slot
    assert len(calls) == n and counts["skipped_slot_filled"] == 2 and counts["stored"] == 0
    assert len(collector.read_jsonl(tmp_path / "index.jsonl")) == 2


def test_identical_content_in_a_new_slot_is_not_stored_twice_but_new_content_is(tmp_path, registry):
    run(tmp_path, registry, lambda u, p, t: FakeResp(make_body()))
    later = T0.replace(day=5, hour=13)                                        # next slot
    c = run(tmp_path, registry, lambda u, p, t: FakeResp(make_body()), now=later)
    assert c["skipped_duplicate_content"] == 2 and c["stored"] == 0
    c = run(tmp_path, registry, lambda u, p, t: FakeResp(make_body(tmin0=21.0)), now=later)
    assert c["stored"] == 2 and len(collector.read_jsonl(tmp_path / "index.jsonl")) == 4


def test_collection_is_resumable_after_partial_failure(tmp_path, registry):
    state = {"n": 0}

    def flaky(url, params, timeout):
        state["n"] += 1
        if params["latitude"] == 12.0 and state["n"] <= 2:
            return FakeResp(b"upstream error", 503)
        return FakeResp(make_body())

    c1 = run(tmp_path, registry, flaky)
    assert c1["stored"] == 1 and c1["errors"] == 1
    c2 = run(tmp_path, registry, flaky)                                       # rerun: only the failed location is retried
    assert c2["stored"] == 1 and c2["skipped_slot_filled"] == 1
    assert {r["location_id"] for r in collector.read_jsonl(tmp_path / "index.jsonl")} == {"B1", "B2"}


# ---- provider errors / missing data / mock exclusion -------------------------------------------------------
@pytest.mark.parametrize("http,kind", [
    (lambda u, p, t: FakeResp(b"oops", 500), "http_error"),
    (lambda u, p, t: FakeResp(b"not json at all"), "invalid_response"),
    (lambda u, p, t: FakeResp(json.dumps({"daily": {"time": ["2026-10-05"]}}).encode()), "invalid_response"),
    (lambda u, p, t: (_ for _ in ()).throw(TimeoutError("slow")), "timeout"),
    (lambda u, p, t: (_ for _ in ()).throw(ConnectionError("down")), "network_error"),
])
def test_provider_errors_are_logged_and_never_become_forecast_records(tmp_path, registry, http, kind):
    c = run(tmp_path, registry, http)
    assert c["stored"] == 0 and c["errors"] == 2
    errs = collector.read_jsonl(tmp_path / "errors.jsonl")
    assert {e["kind"] for e in errs} == {kind} and set(errs[0]) == set(schema.ERROR_FIELDS)
    assert collector.read_jsonl(tmp_path / "index.jsonl") == []              # no fallback data of any kind
    assert not (tmp_path / "raw").exists()


def test_collector_never_imports_mock_or_the_production_fallback_service():
    import ast
    tree = ast.parse(Path(collector.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not [m for m in imported if "mock" in m.lower() or m.endswith("weather.service") or m == "get_point_forecast"]


def test_mock_rows_are_rejected_by_flatten_and_excluded_from_pairs(tmp_path, registry):
    run(tmp_path, registry, lambda u, p, t: FakeResp(make_body()))
    idx = collector.read_jsonl(tmp_path / "index.jsonl")
    idx[0]["is_mock"] = True
    (tmp_path / "index.jsonl").write_text("\n".join(json.dumps(r) for r in idx) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="non-provider"):
        flatten.flatten(tmp_path)
    fc = pd.DataFrame({"is_mock": [True], "record_id": ["x"], "location_id": ["B1"]})
    pairs, drops = pairing.build_pairs(fc.assign(any_value_missing=False), {"locations": []}, pd.DataFrame())
    assert pairs.empty and drops["mock_rows"] == 1


def test_missing_provider_value_stays_missing_and_is_distinguished_from_mock(tmp_path, registry):
    run(tmp_path, registry, lambda u, p, t: FakeResp(make_body(missing_idx=2)))
    df = flatten.flatten(tmp_path)
    row = df[(df["location_id"] == "B1") & (df["target_local_date"] == "2026-10-07")].iloc[0]
    assert np.isnan(row["temperature_min_c"]) and bool(row["any_value_missing"]) and not row["is_mock"]
    assert df["any_value_missing"].sum() == 2                                  # one missing day per block point


# ---- timezone / lead time -------------------------------------------------------------------------------
def test_lead_time_uses_local_days_not_utc_days():
    off = 19800
    # 2026-10-04 20:00 UTC is already 2026-10-05 01:30 in IST
    assert flatten.local_datetime("2026-10-04T20:00:00Z", off).date().isoformat() == "2026-10-05"
    assert flatten.lead_days("2026-10-04T20:00:00Z", off, "2026-10-05") == 0
    assert flatten.lead_days("2026-10-04T20:00:00Z", off, "2026-10-06") == 1
    assert flatten.lead_days("2026-10-04T10:00:00Z", off, "2026-10-05") == 1  # 15:30 IST on the 4th -> next local day is lead 1
    assert flatten.lead_days("2026-10-04T20:00:00Z", 0, "2026-10-05") == 1    # a UTC reading would give a different lead


def test_flattened_table_columns_leads_and_provenance(tmp_path, registry):
    run(tmp_path, registry, lambda u, p, t: FakeResp(make_body()))
    df = flatten.flatten(tmp_path)
    assert list(df.columns) == schema.DAILY_TABLE_FIELDS
    b1 = df[df["location_id"] == "B1"].sort_values("target_local_date")
    assert b1["lead_days"].tolist() == list(range(16)) and b1["retrieval_local_date"].iloc[0] == "2026-10-05"
    assert b1["raw_sha256"].nunique() == 1 and (b1["provider"] == "open-meteo").all()


def test_reference_daily_uses_the_local_ist_day_and_one_source():
    ts = pd.date_range("2026-10-04T00:00:00Z", periods=48, freq="h")
    h = pd.DataFrame({"panchayat_id": "P1", "timestamp_utc": ts, "temperature_c": np.arange(48.0), "rainfall_mm": 0.1,
                      "relative_humidity_pct": 60.0, "wind_speed_kmph": 5.0})
    d = reference.reference_daily_from_hourly(h, "era5_land_cds")
    # IST day 2026-10-05 = UTC 2026-10-04T18:30 .. 2026-10-05T18:30 -> only complete days are kept
    assert set(d["reference_source"]) == {"era5_land_cds"}
    full = d.dropna(subset=["temperature_min_c"])
    assert full["target_local_date"].tolist() == ["2026-10-05"]
    assert full["temperature_min_c"].iloc[0] == 19.0                           # first hour of that IST day is UTC 19:00 (index 19)
    mixed = pd.concat([d, d.assign(reference_source="isd_station")])
    with pytest.raises(ValueError, match="exactly one source"):
        reference.assert_single_source(mixed)


# ---- pairing ---------------------------------------------------------------------------------------------
def test_pairing_matches_reference_day_keeps_lead_and_uses_the_real_production_baseline(tmp_path, registry):
    run(tmp_path, registry, lambda u, p, t: FakeResp(make_body()))
    fc = flatten.flatten(tmp_path)
    days = [(pd.Timestamp("2026-10-05") + pd.Timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)]
    ref = pd.DataFrame({"reference_source": "era5_land_cds", "panchayat_id": "P1", "target_local_date": days,
                        "temperature_min_c": [15.0, 16.0, 17.0], "temperature_max_c": 30.0, "rainfall_mm": 0.0, "humidity_pct": 70.0, "wind_kmph": 10.0})
    pairs, drops = pairing.build_pairs(fc[fc["location_id"] == "B1"], registry, ref)
    assert len(pairs) == 3 and drops["no_reference_day"] == 13
    assert pairs["lead_days"].tolist() == [0, 1, 2] and set(pairs["reference_source"]) == {"era5_land_cds"}
    # production baseline = backend lapse rate: P1 is 500 m above the block's 930 m response elevation (1430 vs 930)
    assert pairs["production_temperature_min_c"].iloc[0] == pytest.approx(20.0 - 0.0065 * (1430.0 - 930.0), abs=0.06)
    assert pairs["block_temperature_min_c"].iloc[0] == 20.0 and pairs["target_temperature_min_c"].iloc[0] == 15.0
    ev = pairing.evaluate_by_lead(pairs)
    assert set(ev) == {0, 1, 2}                                                # leads are never pooled
    assert ev[0]["methods"]["block_as_is"]["mae"] == pytest.approx(5.0)


def test_pairing_drops_forecast_days_with_missing_values_and_counts_them(tmp_path, registry):
    run(tmp_path, registry, lambda u, p, t: FakeResp(make_body(missing_idx=0)))
    fc = flatten.flatten(tmp_path)
    ref = pd.DataFrame({"reference_source": "era5_land_cds", "panchayat_id": "P1", "target_local_date": ["2026-10-05", "2026-10-06"],
                        "temperature_min_c": [15.0, 16.0], "temperature_max_c": 30.0, "rainfall_mm": 0.0, "humidity_pct": 70.0, "wind_kmph": 10.0})
    pairs, drops = pairing.build_pairs(fc[fc["location_id"] == "B1"], registry, ref)
    assert drops["forecast_rows_missing_values"] == 1 and pairs["target_local_date"].tolist() == ["2026-10-06"]


# ---- production parity & readiness gate --------------------------------------------------------------------
def test_collector_request_matches_the_production_provider(monkeypatch):
    from app.weather.providers import open_meteo
    seen = {}

    class R:
        def raise_for_status(self): ...
        def json(self): return json.loads(make_body())

    monkeypatch.setattr(open_meteo.httpx, "get", lambda url, params, timeout: (seen.update(url=url, params=params), R())[1])
    open_meteo.OpenMeteoProvider().get_forecast(13.4, 77.73, 16)
    mine = collector.request_params(13.4, 77.73)
    assert seen["url"] == collector.FORECAST_URL and seen["params"] == mine


def test_readiness_gate_refuses_when_folds_quarters_or_pairs_are_missing():
    reg = locations.load_registry()
    empty = pd.DataFrame(columns=schema.DAILY_TABLE_FIELDS)
    live = readiness.assess(reg, empty, pd.DataFrame(), locations.LIVE, [], [])
    assert live["ready"] is False and live["statement"] == readiness.NOT_READY
    assert live["counts"]["independent_spatial_groups"] == 3                     # the live demo pilot cannot supply 4 folds
    yel = readiness.assess(reg, empty, pd.DataFrame(), locations.YELANDUR, [], [])
    assert yel["counts"]["independent_spatial_groups"] == 4 and yel["ready"] is False
    assert any("pairs" in k or "paired" in k for k in yel["failed_checks"])


def test_registry_separates_block_inputs_from_panchayat_targets_and_flags_demo_data():
    reg = locations.load_registry()
    blocks = locations.block_locations(reg)
    assert {b["location_id"] for b in blocks} == {"BLOCK-DEMO-001", "YELANDUR-BLOCK-PROXY"}
    demo = [l for l in reg["locations"] if l["location_set"] == locations.LIVE]
    assert all(l["is_demo_data"] for l in demo) and len(locations.panchayats_of(reg, "BLOCK-DEMO-001")) == 3
    assert all(l["role"] in ("block", "panchayat") for l in reg["locations"])


def test_location_role_separates_live_demo_geography_from_research_validation_geography():
    reg = locations.load_registry()
    live = [l for l in reg["locations"] if l["location_set"] == locations.LIVE]
    yel = [l for l in reg["locations"] if l["location_set"] == locations.YELANDUR]
    assert live and yel and len(live) + len(yel) == len(reg["locations"])
    assert all(l["location_role"] == "live_demo_pilot" for l in live)
    assert all(l["location_role"] == "research_validation" for l in yel)
    assert all(l["is_demo_data"] is True for l in live) and all(l["is_demo_data"] is False for l in yel)   # unchanged, different meaning
