"""
Stage 5 observational validation (research/stage5_observational_validation/).

Unit tests use synthetic ISD rows / frames (always run). Contract tests read
the committed results; tests needing raw observation files skip if absent.
"""

import json

import numpy as np
import pandas as pd
import pytest
import shapely.geometry as sgeom

from stage5_observational_validation import (
    acquire_observations, criteria5, metrics5, observation_qc, provenance, station_matching, temporal_alignment,
)

RESULTS = station_matching.RESULTS
HEADER = '"STATION","DATE","SOURCE","LATITUDE","LONGITUDE","ELEVATION","NAME","REPORT_TYPE","CALL_SIGN","QUALITY_CONTROL","WND","CIG","VIS","TMP","DEW","SLP","AA1","AA2"\n'


def _row(date, tmp="+0250,1", dew="+0200,1", wnd="240,1,N,0030,1", aa1="", aa2="", rtype="FM-12"):
    return f'"43225099999","{date}","4","14.78","74.13","4.0","KARWAR, IN","{rtype}","99999","V020","{wnd}","","","{tmp}","{dew}","","{aa1}","{aa2}"\n'


def _write(tmp_path, rows):
    p = tmp_path / "s.csv"
    p.write_text(HEADER + "".join(rows), encoding="utf-8")
    return p


# ---------------------------------------------------------------------
# Parsing + QC
# ---------------------------------------------------------------------

def test_parse_scaling_and_units(tmp_path):
    p, _ = observation_qc.parse_station(_write(tmp_path, [_row("2023-01-01T03:00:00")]))
    assert p.at[0, "temperature_c"] == 25.0 and p.at[0, "dewpoint_c"] == 20.0
    assert p.at[0, "wind_speed_kmph"] == pytest.approx(3.0 * 3.6)
    assert str(p.at[0, "time_utc"].tz) == "UTC"


def test_qc_flags_without_deleting(tmp_path):
    rows = [_row("2023-01-01T03:00:00"),
            _row("2023-01-01T03:00:00", rtype="FM-15"),                 # duplicate hour
            _row("2023-01-01T03:30:00"),                                # off-hour
            _row("2023-01-01T06:00:00", tmp="+9999,9"),                 # missing sentinel
            _row("2023-01-01T09:00:00", tmp="+0250,3"),                 # erroneous QC
            _row("2023-01-01T12:00:00", tmp="+0700,1"),                 # outside limits
            _row("2023-01-01T15:00:00", tmp="+0200,1", dew="+0250,1")]  # dewpoint > temperature
    p, _ = observation_qc.parse_station(_write(tmp_path, rows))
    q = observation_qc.qc_points(p)
    assert len(q) == len(rows)  # nothing deleted
    assert q["temperature_c_status"].tolist()[:6] == ["OK", "DUPLICATE_HOUR", "OFF_HOUR_REPORT", "MISSING_SENTINEL",
                                                      "REJECTED_SOURCE_QC", "OUTSIDE_PHYSICAL_LIMITS"]
    assert q.at[6, "dewpoint_c_status"] == "DEWPOINT_ABOVE_TEMPERATURE"
    assert q.at[0, "relative_humidity_pct_status"] == "OK" and 0 < q.at[0, "relative_humidity_pct"] < 100


def test_rain_qc_uses_source_definitions(tmp_path):
    rows = [_row("2023-01-01T03:00:00", aa1="03,0012,9,1"),   # accepted 1.2 mm / 3 h
            _row("2023-01-01T06:00:00", aa1="06,0050,3,1"),   # condition 3: amount missing until end -> not used
            _row("2023-01-01T09:00:00", aa1="09,0010,9,1"),   # 9-h period not accepted
            _row("2023-01-01T12:00:00", aa1="24,0000,2,1")]   # trace -> 0.0, flagged
    _, r = observation_qc.parse_station(_write(tmp_path, rows))
    q = observation_qc.qc_rain(r)
    assert q["status"].tolist() == ["OK", "CONDITION_NOT_USABLE", "PERIOD_NOT_ACCEPTED", "OK"]
    assert q.at[0, "depth_mm"] == pytest.approx(1.2) and q.at[3, "depth_mm"] == 0.0 and q.at[3, "trace"]


# ---------------------------------------------------------------------
# Alignment (no interpolation, no filling)
# ---------------------------------------------------------------------

def _model(hours=10):
    idx = pd.date_range("2023-01-01", periods=hours, freq="h", tz="UTC")
    return pd.DataFrame({"A1_bilinear": np.arange(hours, dtype=float), "C4": np.ones(hours)}, index=idx)


def test_point_alignment_exact_hours_only():
    obs = pd.DataFrame({"time_utc": pd.to_datetime(["2023-01-01T03:00Z", "2023-01-01T05:00Z", "2023-01-02T00:00Z"], utc=True),
                        "temperature_c": [20.0, 21.0, 22.0], "temperature_c_status": ["OK", "REJECTED_SOURCE_QC", "OK"]})
    j = temporal_alignment.align_points(obs, "temperature_c", _model())
    assert len(j) == 1 and j["observed"].iloc[0] == 20.0 and j["A1_bilinear"].iloc[0] == 3.0


def test_rain_alignment_sums_period_and_drops_incomplete():
    rain = pd.DataFrame({"time_utc": pd.to_datetime(["2023-01-01T05:00Z", "2023-01-01T02:00Z"], utc=True),
                         "period_h": [3, 6], "depth_mm": [4.0, 1.0], "status": ["OK", "OK"], "trace": [False, False]})
    pairs, dropped = temporal_alignment.align_rain(rain, _model())
    assert dropped == 1 and len(pairs) == 1
    assert pairs["A1_bilinear"].iloc[0] == 3 + 4 + 5  # hours ending 03,04,05
    assert pairs["C4"].iloc[0] == 3.0


# ---------------------------------------------------------------------
# Metrics + bootstrap
# ---------------------------------------------------------------------

def test_point_and_rain_metrics():
    m = metrics5.point_metrics(np.array([1.0, 3.0]), np.array([2.0, 2.0]))
    assert (m["n"], m["mae"], m["bias"], m["median_abs_error"]) == (2, 1.0, 0.0, 1.0)
    r = metrics5.rain_metrics(np.array([0.0, 2.0, -0.1]), np.array([0.0, 3.0, 0.0]), np.array([3, 3, 3]))
    assert r["wet_periods_observed"] == 1 and r["negative_predictions"] == 1 and r["false_wet_rate"] == 0.0


def test_block_bootstrap_is_deterministic_and_station_separated():
    rng = np.random.default_rng(0)
    days = np.repeat(pd.date_range("2023-01-01", periods=60).to_numpy(), 8)
    g1 = (rng.normal(-0.2, 1, len(days)), days)
    g2 = (rng.normal(0.1, 1, len(days) // 2), days[: len(days) // 2])
    a = metrics5.paired_bootstrap([g1, g2], reps=200)
    b = metrics5.paired_bootstrap([g1, g2], reps=200)
    assert a == b and a["n_stations"] == 2 and a["n_hours"] == len(g1[0]) + len(g2[0])
    assert a["ci95"][0] <= a["mean_diff"] <= a["ci95"][1]


def test_seasons_cover_all_months():
    ts = pd.Series(pd.date_range("2023-01-15", periods=12, freq="MS", tz="UTC"))
    assert metrics5.season_of(ts).notna().all()


# ---------------------------------------------------------------------
# Matching rules (synthetic geography)
# ---------------------------------------------------------------------

def _areas():
    poly = sgeom.box(77.0, 12.0, 77.1, 12.1)
    gp = {"gp_code": "1", "gp_name": "G", "geometry": poly, "cell": "E5L_12.00N_77.00E",
          "centroid": (12.05, 77.05), "elevation_mean_m": 700.0}
    return {"T": {"tp_code": "T", "tp_name": "Area", "district": "D", "region": "R",
                  "cells": {"E5L_12.00N_77.00E", "E5L_12.10N_77.10E"}, "gps": [gp], "union": poly}}


def _st(lat, lon):
    return pd.Series({"station_id": "x", "station_name": "S", "latitude": lat, "longitude": lon, "elevation_m": 650.0})


def test_matching_primary_diagnostic_excluded():
    a = _areas()
    assert station_matching.match_station(_st(12.04, 77.04), a, set())["match_set"] == "PRIMARY"
    near = station_matching.match_station(_st(12.24, 77.24), a, set())
    assert near["match_set"] == "NEARBY_DIAGNOSTIC" and near["gp_code"] == "1"
    far = station_matching.match_station(_st(15.0, 75.0), a, {"E5L_15.00N_75.00E"})
    assert far["match_set"] == "EXCLUDED" and "Yelandur" in far["reason"]


def test_criteria_are_frozen_values():
    assert criteria5.EVAL_START_UTC.startswith("2023-01-01") and criteria5.ADJACENT_CELLS == 1
    assert {"2", "3", "6", "7"}.isdisjoint(criteria5.ACCEPTED_QC)
    assert criteria5.MIN_STATION_HOURS_FOR_METRICS == 500


# ---------------------------------------------------------------------
# Contract tests on committed outputs
# ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def results():
    p = RESULTS / "stage5_results.json"
    if not p.exists():
        pytest.skip("stage5_results.json not generated")
    return json.loads(p.read_text(encoding="utf-8"))


def test_framing_terminology_and_karwar(results):
    assert results["framing"] == ("Stage 4D was evaluated against the ERA5-Land reanalysis proxy. Stage 5 evaluates "
                                  "the frozen Stage 4D model against independent observations.")
    assert "below the frozen >= 6-cell criterion" in results["karwar_exception"]
    for f in ("stage5_results.json", "provenance.json", "observation_qc_report.json", "observation_source_manifest.json"):
        assert "ground truth" not in (RESULTS / f).read_text(encoding="utf-8").lower()


def test_primary_and_diagnostic_sets_kept_separate(results):
    m = pd.read_csv(RESULTS / "station_matching.csv", dtype=str)
    assert results["primary_matched_station_count"] == int((m["match_set"] == "PRIMARY").sum())
    assert {s["match_set"] for s in results["diagnostic_stations"]} <= {"PRIMARY", "NEARBY_DIAGNOSTIC"}
    if results["primary_matched_station_count"] == 0:
        assert "EMPTY" in results["primary_set_note"]


def test_gate6_frozen_model_reproduced(results):
    g = results["frozen_model"]["gate6_reproduction"]
    assert g and all(x["reproduced"] and not x["mismatches"] and x["compared"] == 15 for x in g)
    assert results["frozen_model"]["random_state"] == 0


@pytest.fixture(scope="module")
def prov():
    p = RESULTS / "provenance.json"
    if not p.exists():
        pytest.skip("provenance.json not generated")
    return json.loads(p.read_text(encoding="utf-8"))


def test_independence_audit_passed(prov):
    chk = prov["independence_checks"]
    assert chk["stage4c_dataset_manifest_unchanged"] and chk["all_observation_files_written_after_stage4d"]
    assert chk["no_development_code_references_observations"] and chk["frozen_predictions_reproduced"]
    assert provenance.code_reference_audit()["references_found"] == []


def test_observation_files_match_provenance_hashes(prov):
    checked = 0
    for rec in prov["files"].values():
        p = acquire_observations.REPO / rec["file"]
        if p.exists():
            assert acquire_observations.sha256(p) == rec["sha256"]
            checked += 1
    if not checked:
        pytest.skip("raw observation files not present locally")


def test_outcomes_follow_rule(results):
    for v, label in results["outcome_by_variable"].items():
        assert label in {"SUPPORTED", "CONTRADICTED", "MIXED", "INSUFFICIENT"}
        if v == "rainfall_mm":
            continue
        a1 = results["uncertainty"][v]["C4_minus_A1_bilinear"]["pooled"]["ci95"]
        a2 = results["uncertainty"][v]["C4_minus_A2_nearest"]["pooled"]["ci95"]
        expected = ("SUPPORTED" if a1[1] < 0 and a2[1] < 0 else "CONTRADICTED" if a1[0] > 0 and a2[0] > 0 else "MIXED")
        assert label == expected


def test_insufficient_stations_not_pooled(results):
    st = pd.read_csv(RESULTS / "station_level_results.csv")
    for v, pooled in results["pooled_sufficient_stations"].items():
        small = st[(st["variable"] == v) & (~st["sufficient_sample"])]["station_id"].astype(str).unique()
        assert not set(small) & set(pooled["stations"])


# ---------------------------------------------------------------------
# Recovery design: Gate 6 as its own checkpointed, observable step
# ---------------------------------------------------------------------

from stage5_observational_validation import evaluate_frozen_model, gate6  # noqa: E402
from stage4d_ml import splits4d  # noqa: E402

FOLD = "taluka_6253"  # real Stage 4D fold file -> identity hashes are real


def _good_record(pred_path, **over):
    rec = {"fold_id": FOLD, "compared": gate6.EXPECTED_COMPARISONS, "mismatches": [], "reproduced": True,
           "keep_gps": ["X"], "predictions_sha256": gate6.sha256_file(pred_path), **gate6.current_identity(FOLD)}
    rec.update(over)
    return rec


def _synthetic_predictions():
    rows = []
    for v in gate6.VARIABLES:
        for h in range(3):
            rows.append({"panchayat_lgd_code": "X", "timestamp_utc": pd.Timestamp("2023-01-01", tz="UTC") + pd.Timedelta(hours=h),
                         "A1_bilinear": 1.0, "A2_nearest": 2.0, "C4": 3.0, gate6.REFERENCE: 4.0, "variable": v})
    return pd.DataFrame(rows)


def test_checkpoint_validation_detects_every_problem(tmp_path):
    pred = tmp_path / "p.parquet"
    _synthetic_predictions().to_parquet(pred)
    ident = gate6.current_identity(FOLD)
    assert gate6.validate_checkpoint(_good_record(pred), ident, pred) == []
    assert gate6.validate_checkpoint(_good_record(pred, reproduced=False), ident, pred)
    assert gate6.validate_checkpoint(_good_record(pred, mismatches=["temperature_c/C4"]), ident, pred)
    assert gate6.validate_checkpoint(_good_record(pred, compared=14), ident, pred)
    assert gate6.validate_checkpoint(_good_record(pred, stage4d_fold_file_sha256="0" * 64), ident, pred)
    assert gate6.validate_checkpoint(_good_record(pred, dataset_manifest_sha256="0" * 64), ident, pred)
    assert gate6.validate_checkpoint(_good_record(pred, predictions_sha256="0" * 64), ident, pred)
    assert gate6.validate_checkpoint(_good_record(pred), ident, tmp_path / "missing.parquet")


def test_checkpoint_round_trip_and_tamper_detection(tmp_path, monkeypatch):
    monkeypatch.setattr(gate6, "CHECKPOINTS", tmp_path)
    assert gate6.load_checkpoint(FOLD) is None  # nothing recorded yet
    rec = gate6.save_checkpoint(FOLD, _synthetic_predictions(),
                                {"fold_id": FOLD, "compared": 15, "mismatches": [], "reproduced": True, "keep_gps": ["X"]})
    preds, loaded = gate6.load_checkpoint(FOLD)
    assert set(preds) == set(gate6.VARIABLES) and len(preds["temperature_c"]) == 3
    assert loaded["predictions_sha256"] == rec["predictions_sha256"]
    assert (tmp_path / f"gate6_{FOLD}.json").exists()
    (tmp_path / f"gate6_{FOLD}_predictions.parquet").write_bytes(b"corrupt")
    assert gate6.load_checkpoint(FOLD) is None  # tampered/corrupt checkpoint is never reused


def test_run_gate6_reuses_valid_checkpoint_without_loading_data(tmp_path, monkeypatch):
    monkeypatch.setattr(gate6, "CHECKPOINTS", tmp_path)
    monkeypatch.setattr(gate6, "GATE6_REPORT", tmp_path / "gate6_report.json")
    gate6.save_checkpoint(FOLD, _synthetic_predictions(),
                          {"fold_id": FOLD, "compared": 15, "mismatches": [], "reproduced": True, "keep_gps": ["X"]})

    def boom():
        raise AssertionError("data must not be loaded when a valid checkpoint exists")

    monkeypatch.setattr(gate6.data4d, "load_stage4_wide", boom)
    monkeypatch.setattr(gate6.data4d, "verify_dataset_identity", boom)
    stations = pd.DataFrame({"tp_code": ["6253"], "gp_code": ["X"]})
    records = gate6.run_gate6(stations)
    assert len(records) == 1 and records[0]["reproduced"]
    assert json.loads((tmp_path / "gate6_report.json").read_text())["passed"] is True


def _tiny_wide():
    t = pd.date_range("2023-01-01", periods=3, freq="h", tz="UTC")
    rows = []
    for tp, gp, period in (("6253", "X", "test_period"), ("6253", "Y", "test_period"), ("6142", "Z", "train_period")):
        for ts in t:
            rows.append({"panchayat_lgd_code": gp, "taluka_panchayat_lgd_code": tp, "timestamp_utc": ts,
                         "temporal_period": period, **{f"target_{v}": 1.0 for v in gate6.VARIABLES}})
    return pd.DataFrame(rows)


def test_compute_fold_stops_on_hash_mismatch(monkeypatch):
    monkeypatch.setattr(gate6.train4d, "fit_and_predict",
                        lambda wide, train, test, v, methods=None: ({m: np.zeros(int(test.sum())) for m in methods}, None, None))
    with pytest.raises(RuntimeError, match="not reproduced"):
        gate6.compute_fold(_tiny_wide(), FOLD, ["X"])


def test_compute_fold_hashes_full_vector_then_keeps_only_station_gps(monkeypatch):
    stored = json.loads((gate6.STAGE4D_AREA / f"{FOLD}.json").read_text(encoding="utf-8"))
    seen = {}

    def fake_hash(arr):
        seen["n"] = len(arr)  # the hash is taken over ALL held-out Panchayats' rows, before any subsetting
        return "H"

    monkeypatch.setattr(gate6.train4d, "fit_and_predict",
                        lambda wide, train, test, v, methods=None: ({m: np.ones(int(test.sum())) for m in methods}, None, None))
    monkeypatch.setattr(gate6.metrics4d, "prediction_hash", fake_hash)
    # make the stored Stage 4D hashes equal the stand-in so the comparison passes
    real_load = json.loads

    def patched_stored(text, *a, **k):
        d = real_load(text, *a, **k)
        if isinstance(d, dict) and "variables" in d:
            for v in d["variables"].values():
                for m in v["metrics"].values():
                    m["prediction_sha256"] = "H"
        return d

    monkeypatch.setattr(gate6.json, "loads", patched_stored)
    preds, rec = gate6.compute_fold(_tiny_wide(), FOLD, ["X"])
    assert seen["n"] == 6 and rec["reproduced"] and rec["compared"] == 15  # 2 Panchayats x 3 hours hashed together
    assert set(preds["panchayat_lgd_code"]) == {"X"} and len(preds) == 3 * len(gate6.VARIABLES)
    assert stored["variables"]  # real file untouched by the patch


def test_evaluate_refuses_to_start_without_gate6_and_reads_no_observations(tmp_path, monkeypatch):
    monkeypatch.setattr(gate6, "CHECKPOINTS", tmp_path)  # empty -> Gate 6 not recorded
    monkeypatch.setattr(evaluate_frozen_model.data4d, "verify_dataset_identity", lambda: {})

    def no_observations():
        raise AssertionError("observations must not be touched before Gate 6 is recorded")

    monkeypatch.setattr(evaluate_frozen_model.acquire_observations, "run", no_observations)
    monkeypatch.setattr(evaluate_frozen_model.observation_qc, "parse_station", lambda *a, **k: no_observations())
    with pytest.raises(RuntimeError, match="Gate 6 is not recorded"):
        evaluate_frozen_model.evaluate()


def test_progress_log_is_timestamped_and_flushed(capsys):
    gate6.log("hello")
    out = capsys.readouterr().out
    assert out.startswith("[") and "] hello" in out and out.endswith("\n")


def test_evaluator_no_longer_refits_models():
    src = (evaluate_frozen_model.MODULE / "evaluate_frozen_model.py").read_text(encoding="utf-8")
    assert "fit_and_predict" not in src and "load_stage4_wide" not in src
    assert "--step" in src and "gate6" in src


# ---------------------------------------------------------------------
# Bootstrap speed fix must not change any number
# ---------------------------------------------------------------------

def _reference_bootstrap(groups, reps, seed):
    """The original (slow) implementation, kept here as the numerical reference."""
    groups = [(np.asarray(d, float), np.asarray(k)) for d, k in groups if len(d)]
    total_n = sum(len(d) for d, _ in groups)
    point = float(sum(d.sum() for d, _ in groups) / total_n)
    rng = np.random.default_rng(seed)
    stats = np.empty(reps)
    for r in range(reps):
        s, n = 0.0, 0
        for d, days in groups:
            idx = metrics5._block_indices(days, rng)
            s += d[idx].sum()
            n += len(idx)
        stats[r] = s / n
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return point, [float(lo), float(hi)]


def test_fast_bootstrap_matches_reference_for_naive_and_tz_aware_day_labels():
    rng = np.random.default_rng(5)
    idx = pd.date_range("2023-01-01", periods=24 * 40, freq="h", tz="UTC")
    d1 = rng.normal(-0.1, 1, len(idx))
    idx2 = idx[::3]
    d2 = rng.normal(0.2, 1, len(idx2))
    naive = lambda i: i.floor("D").tz_localize(None).to_numpy()  # noqa: E731
    aware = lambda i: pd.Series(i).dt.floor("D").to_numpy()      # object array, as in the real run  # noqa: E731
    assert aware(idx).dtype == object
    ref_point, ref_ci = _reference_bootstrap([(d1, naive(idx)), (d2, naive(idx2))], 300, 123)
    for label in (naive, aware):
        got = metrics5.paired_bootstrap([(d1, label(idx)), (d2, label(idx2))], reps=300, seed=123)
        assert got["mean_diff"] == pytest.approx(ref_point, rel=0, abs=1e-15)
        assert got["ci95"] == ref_ci  # identical draws -> identical interval


def test_prepared_block_indices_equal_original_selection():
    days = pd.date_range("2023-01-01", periods=50, freq="D").repeat(7).to_numpy()
    prep = metrics5._prepare_days(days)
    for seed in range(5):
        a = metrics5._block_indices(days, np.random.default_rng(seed))
        b = metrics5._block_indices_prepared(prep, np.random.default_rng(seed))
        assert np.array_equal(a, b)
