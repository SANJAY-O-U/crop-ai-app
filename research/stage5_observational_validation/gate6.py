"""
Stage 5 Gate 6: frozen-model reproduction, as its OWN resumable step.

For every Stage 4D area fold that holds out a matched station's area, the
fold is re-fitted with the UNCHANGED Stage 4D code (stage4d_ml.train4d, C4 =
ml_stage2 CONFIG, random_state 0) and the full test-set prediction hash of
A1, A2 and C4 for every variable must equal the hash Stage 4D recorded.
Observations are never read here.

Recovery design (after the 30 Sep stall, where an in-memory-only run left no
trace):
  * progress is logged with timestamps and flushed (run with `python -u`,
    redirected to a file -- never through a pipe that buffers);
  * each fold is checkpointed as soon as it is verified:
        results/checkpoints/gate6_<fold>.json                 (written LAST = fold complete)
        results/checkpoints/gate6_<fold>_predictions.parquet  (only the stations' Panchayats)
  * a checkpoint is reused only if it re-validates against the CURRENT Stage 4D
    fold file, Stage 4C dataset manifest and design manifest, and its
    predictions file still matches its recorded SHA-256; otherwise the fold
    is recomputed. Predictions are deterministic, so reuse and recompute give
    identical values.

    python research/stage5_observational_validation/evaluate_frozen_model.py --step gate6
"""

import hashlib
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from ml_stage2.features import VARIABLES  # noqa: E402
from stage4d_ml import data4d, metrics4d, splits4d, train4d  # noqa: E402

MODULE = Path(__file__).resolve().parent
RESULTS = MODULE / "results"
CHECKPOINTS = RESULTS / "checkpoints"
GATE6_REPORT = RESULTS / "gate6_report.json"
STAGE4D_AREA = _RESEARCH_DIR / "stage4d_ml" / "results" / "area"
METHODS = ["A1_bilinear", "A2_nearest", "C4"]
REFERENCE = "ERA5L_target"  # the Stage 4 target itself, kept as a control column (not a method)
EXPECTED_COMPARISONS = len(VARIABLES) * len(METHODS)


def log(msg: str) -> None:
    """Timestamped, flushed progress line (plus resident memory when psutil exists)."""
    rss = ""
    try:
        import psutil

        rss = f" [rss {psutil.Process().memory_info().rss / 1e6:,.0f} MB]"
    except Exception:  # psutil is optional
        pass
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}{rss}", flush=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_stations() -> pd.DataFrame:
    m = pd.read_csv(RESULTS / "station_matching.csv", dtype={"station_id": str, "gp_code": str, "tp_code": str})
    return m[m["match_set"] != "EXCLUDED"].reset_index(drop=True)


# ---------------------------------------------------------------------
# Checkpoints
# ---------------------------------------------------------------------

def checkpoint_files(fold_id: str) -> tuple[Path, Path]:
    return CHECKPOINTS / f"gate6_{fold_id}.json", CHECKPOINTS / f"gate6_{fold_id}_predictions.parquet"


def current_identity(fold_id: str) -> dict:
    return {"stage4d_fold_file_sha256": sha256_file(STAGE4D_AREA / f"{fold_id}.json"),
            "dataset_manifest_sha256": sha256_file(data4d.DATASET_MANIFEST),
            "design_manifest_sha256": sha256_file(data4d.DESIGN_MANIFEST)}


def validate_checkpoint(rec: dict, identity: dict, predictions_path: Path) -> list[str]:
    """Pure check; returns the list of problems (empty = reusable)."""
    problems = []
    if rec.get("reproduced") is not True or rec.get("mismatches"):
        problems.append("hashes were not reproduced")
    if rec.get("compared") != EXPECTED_COMPARISONS:
        problems.append(f"compared {rec.get('compared')} hashes, expected {EXPECTED_COMPARISONS}")
    for key, value in identity.items():
        if rec.get(key) != value:
            problems.append(f"{key} differs from the current file")
    if not Path(predictions_path).exists():
        problems.append("predictions file missing")
    elif sha256_file(predictions_path) != rec.get("predictions_sha256"):
        problems.append("predictions file SHA-256 differs from the record")
    return problems


def load_checkpoint(fold_id: str) -> tuple[dict, dict] | None:
    """({variable: DataFrame}, record) for a valid checkpoint, else None."""
    rec_path, pred_path = checkpoint_files(fold_id)
    if not rec_path.exists():
        return None
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    problems = validate_checkpoint(rec, current_identity(fold_id), pred_path)
    if problems:
        log(f"checkpoint {fold_id} rejected: {problems}")
        return None
    frame = pd.read_parquet(pred_path)
    return {v: g.drop(columns="variable").reset_index(drop=True) for v, g in frame.groupby("variable")}, rec


# ---------------------------------------------------------------------
# One fold
# ---------------------------------------------------------------------

def compute_fold(wide: pd.DataFrame, fold_id: str, keep_gps: list[str]) -> tuple[pd.DataFrame, dict]:
    """Re-fits one Stage 4D area fold and compares the full-test-set
    prediction hashes with Stage 4D's. Returns (station-Panchayat predictions
    in long form, check record). Raises on any hash mismatch."""
    stored = json.loads((STAGE4D_AREA / f"{fold_id}.json").read_text(encoding="utf-8"))
    fold = next(f for f in splits4d.fold_definitions()["area"] if f["fold_id"] == fold_id)
    expected, computed, mismatches, frames = {}, {}, [], []
    t0 = time.time()
    for v in VARIABLES:
        train, test = splits4d.masks(wide, "area", fold, v)
        log(f"  {fold_id} {v}: {int(train.sum()):,} train rows, {int(test.sum()):,} test rows -> fitting A1/A2/C4")
        preds, _, _ = train4d.fit_and_predict(wide, train, test, v, methods=METHODS)
        bad = []
        for m in METHODS:
            key = f"{v}/{m}"
            expected[key] = stored["variables"][v]["metrics"][m]["prediction_sha256"]
            computed[key] = metrics4d.prediction_hash(preds[m])
            if computed[key] != expected[key]:
                bad.append(key)
        mismatches += bad
        frame = wide.loc[test, ["panchayat_lgd_code", "timestamp_utc"]].copy()
        frame["panchayat_lgd_code"] = frame["panchayat_lgd_code"].astype(str)
        for m in METHODS:
            frame[m] = preds[m]
        frame[REFERENCE] = wide.loc[test, f"target_{v}"].to_numpy(dtype=float)
        frame["variable"] = v
        frames.append(frame[frame["panchayat_lgd_code"].isin(keep_gps)])  # subset AFTER the full-vector hash
        log(f"  {fold_id} {v}: done in {time.time() - t0:,.0f}s total; hashes {'OK' if not bad else 'MISMATCH ' + str(bad)}")
    record = {"fold_id": fold_id, "compared": len(expected), "mismatches": mismatches,
              "reproduced": not mismatches, "expected_hashes": expected, "computed_hashes": computed,
              "keep_gps": sorted(keep_gps), "elapsed_s": round(time.time() - t0, 1)}
    if mismatches:
        raise RuntimeError(f"STOP (Gate 6): frozen Stage 4D predictions not reproduced for {fold_id}: {mismatches}")
    return pd.concat(frames, ignore_index=True), record


def save_checkpoint(fold_id: str, predictions: pd.DataFrame, record: dict) -> dict:
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    rec_path, pred_path = checkpoint_files(fold_id)
    tmp = pred_path.with_suffix(".tmp")
    predictions.to_parquet(tmp, index=False)
    tmp.replace(pred_path)
    record = {**record, **current_identity(fold_id), "predictions_file": pred_path.name,
              "predictions_sha256": sha256_file(pred_path), "prediction_rows": int(len(predictions)),
              "completed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "versions": {"python": platform.python_version(), "pandas": pd.__version__}}
    rec_path.write_text(json.dumps(record, indent=1), encoding="utf-8")  # last: its presence marks the fold complete
    return record


# ---------------------------------------------------------------------
# The step
# ---------------------------------------------------------------------

def run_gate6(stations: pd.DataFrame | None = None) -> list[dict]:
    stations = load_stations() if stations is None else stations
    fold_gps = {f"taluka_{tp}": sorted(set(g["gp_code"])) for tp, g in stations.groupby("tp_code")}
    log(f"Gate 6: {len(fold_gps)} fold(s) to verify: {sorted(fold_gps)}")
    wide, records = None, []
    for fold_id in sorted(fold_gps):
        cp = load_checkpoint(fold_id)
        if cp is not None and set(fold_gps[fold_id]) <= set(cp[1]["keep_gps"]):
            log(f"Gate 6 {fold_id}: valid checkpoint found -> reused (no refit)")
            records.append(cp[1])
            continue
        if wide is None:
            log("verifying Stage 4C dataset identity (SHA-256 of all Parquet files)")
            data4d.verify_dataset_identity()
            log("loading the Stage 4C wide frame (about 1.5 GB; takes 1-2 minutes)")
            wide = data4d.load_stage4_wide()
            log(f"wide frame loaded: {len(wide):,} rows")
        log(f"Gate 6 {fold_id}: computing (Panchayats kept for stations: {fold_gps[fold_id]})")
        preds, rec = compute_fold(wide, fold_id, fold_gps[fold_id])
        records.append(save_checkpoint(fold_id, preds, rec))
        log(f"Gate 6 {fold_id}: VERIFIED and checkpointed ({rec['compared']}/{EXPECTED_COMPARISONS} hashes identical)")
    if wide is not None:
        del wide
    report = {"gate": 6, "passed": all(r["reproduced"] and r["compared"] == EXPECTED_COMPARISONS for r in records),
              "folds": [{k: r.get(k) for k in ("fold_id", "compared", "mismatches", "reproduced", "elapsed_s",
                                               "stage4d_fold_file_sha256", "predictions_sha256", "completed_utc")}
                        for r in records],
              "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "note": "Observations are not read in this step."}
    GATE6_REPORT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    log(f"Gate 6 {'PASSED' if report['passed'] else 'FAILED'} -> {GATE6_REPORT.name}")
    return records
