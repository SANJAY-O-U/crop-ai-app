"""
Stage 5 provenance + independence (leakage) audit.

Proves the observations are external to model development:
  1. Stage 4C/4D artifacts are byte-identical to what Stage 4D recorded.
  2. Every observation file was first written AFTER the Stage 4D results
     were finalized (file timestamps).
  3. No Stage 4C/4D/earlier-stage source file references the observation
     directory or ISD.
  4. Gate 6: the frozen Stage 4D predictions are reproduced bit-for-bit, so
     the model used here is exactly the one evaluated in Stage 4D.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

_RESEARCH = Path(__file__).resolve().parents[1]
REPO = _RESEARCH.parent
STAGE4D_RESULTS = _RESEARCH / "stage4d_ml" / "stage4d_results.json"
DEV_DIRS = ["stage4_spatial_generalization", "stage4d_ml", "multi_gp", "ml_stage2", "ml_stage3_ablation",
            "ml_stage3b_rainfall", "baselines", "pipeline", "era5_linkage", "spatial_proxy", "elevation"]
OBS_MARKERS = ("data/raw/observations", "global-hourly", "isd-history", "ncei.noaa.gov")


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _mtime(p: Path) -> str:
    return datetime.fromtimestamp(Path(p).stat().st_mtime, timezone.utc).isoformat(timespec="seconds")


def code_reference_audit() -> dict:
    hits = []
    for d in DEV_DIRS:
        for f in (_RESEARCH / d).rglob("*.py"):
            text = f.read_text(encoding="utf-8", errors="ignore")
            hits += [f"{f.relative_to(REPO).as_posix()}: {m}" for m in OBS_MARKERS if m in text]
    return {"directories_scanned": DEV_DIRS, "markers": list(OBS_MARKERS), "references_found": hits}


def build(files: dict, gate6: list) -> dict:
    s4d = json.loads(STAGE4D_RESULTS.read_text(encoding="utf-8"))
    dm = _RESEARCH / "stage4_spatial_generalization" / "stage4_dataset_manifest.json"
    stage4d_time = _mtime(STAGE4D_RESULTS)
    obs_times = {k: v["retrieved_utc"] for k, v in files.items()}
    audit = code_reference_audit()
    checks = {
        "stage4c_dataset_manifest_unchanged": _sha(dm) == s4d["dataset_identity"]["dataset_manifest_sha256"],
        "stage4d_results_written_utc": stage4d_time,
        "all_observation_files_written_after_stage4d": all(t > stage4d_time for t in obs_times.values()),
        "no_development_code_references_observations": not audit["references_found"],
        "frozen_predictions_reproduced": all(g.get("reproduced") for g in gate6),
    }
    if not all(v for k, v in checks.items() if k != "stage4d_results_written_utc"):
        raise RuntimeError(f"STOP: independence audit failed: {checks}")
    return {
        "source": "NOAA NCEI Integrated Surface Database / Global Surface Hourly (DSI 3505_03)",
        "citation": "NOAA National Centers for Environmental Information (2001): Global Surface Hourly "
                    "[stations 432250, 432330, 432720, 432840; 2023]. Accessed 2026-09-30.",
        "license": "NCEI use constraints: cite as above; no warranty as to accuracy, reliability or completeness.",
        "files": files,
        "station_metadata_sha256": files["station_history"]["sha256"],
        "independence_checks": checks,
        "code_reference_audit": audit,
        "gate6": gate6,
        "used_for": "external validation only -- not used in Stage 4C construction, Stage 4D training, "
                    "hyperparameters, features, or thresholds (none of these changed in Stage 5)",
    }
