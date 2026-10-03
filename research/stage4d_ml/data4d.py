"""
Loads the frozen Stage 4C dataset (and the Phase 2D Yelandur reference) into
a compact WIDE table: one row per Panchayat x UTC hour, with the target and
the coarse ERA5 values of all 5 variables as columns. Read-only.

Identity is verified before anything else: every Parquet file's SHA-256 must
equal the value recorded in the frozen stage4_dataset_manifest.json, and the
row counts must match.
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from ml_stage2.features import COARSE_FEATURES, STATIC_FEATURES, VARIABLES, time_features  # noqa: E402

REPO = _RESEARCH_DIR.parent
S4 = _RESEARCH_DIR / "stage4_spatial_generalization"
DESIGN_MANIFEST = S4 / "stage4_acquisition_manifest.json"
DATASET_MANIFEST = S4 / "stage4_dataset_manifest.json"
ACQ_RECORD = S4 / "stage4c_acquisition_record.json"
PHASE2D_PARQUET = REPO / "data" / "training" / "yelandur_multi_gp.parquet"
PHASE2D_MANIFEST = _RESEARCH_DIR / "multi_gp" / "yelandur_multi_gp_manifest.json"

HOURS = 26280
KEY_COLS = ["panchayat_lgd_code", "timestamp_utc"]
STATIC_EXTRA = ["coarse_nearest_distance_km"]
ID_COLS = ["taluka_panchayat_lgd_code", "zila_panchayat_lgd_code", "district_name", "geographic_regime",
           "cell_group_id", "temporal_period", "taluka_holdout_fold", "district_holdout_fold",
           "regional_holdout_fold", "cell_diagnostic_fold"]
LONG_COLS = KEY_COLS + ID_COLS + STATIC_FEATURES + STATIC_EXTRA + [
    "variable", "target_value", "coarse_bilinear_value", "coarse_nearest_value", "target_rainfall_clamped"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_dataset_identity() -> dict:
    """Every Stage 4 Parquet file must match its recorded SHA-256 and row count."""
    m = load_json(DATASET_MANIFEST)
    files = []
    for a in m["dataset_files"]:
        p = REPO / a["file"]
        if not p.exists():
            raise FileNotFoundError(f"STOP: {a['file']} missing")
        actual = sha256(p)
        if actual != a["sha256"]:
            raise RuntimeError(f"STOP: {a['file']} SHA-256 {actual} != manifest {a['sha256']}")
        n = pq.ParquetFile(p).metadata.num_rows
        if n != a["rows"]:
            raise RuntimeError(f"STOP: {a['file']} has {n} rows, manifest says {a['rows']}")
        files.append({"tp_code": a["tp_code"], "file": a["file"], "sha256": actual, "rows": n})
    total = sum(f["rows"] for f in files)
    if total != m["row_total"]:
        raise RuntimeError(f"STOP: total rows {total} != manifest {m['row_total']}")
    return {"dataset_manifest": DATASET_MANIFEST.relative_to(REPO).as_posix(),
            "dataset_manifest_sha256": sha256(DATASET_MANIFEST),
            "design_manifest_sha256": sha256(DESIGN_MANIFEST),
            "acquisition_record_sha256": sha256(ACQ_RECORD),
            "row_total": total, "files": files}


def _widen(long: pd.DataFrame, static_cols: list[str], id_cols: list[str]) -> pd.DataFrame:
    """Long (GP x hour x variable) -> wide (GP x hour)."""
    vals = long.pivot(index=KEY_COLS, columns="variable",
                      values=["target_value", "coarse_bilinear_value", "coarse_nearest_value"])
    wide = pd.DataFrame(index=vals.index)
    for v in VARIABLES:
        wide[f"target_{v}"] = vals[("target_value", v)].astype("float64")
        wide[f"era5_{v}"] = vals[("coarse_bilinear_value", v)].astype("float64")
        wide[f"nearest_{v}"] = vals[("coarse_nearest_value", v)].astype("float64")
    rain = long[long["variable"] == "rainfall_mm"].set_index(KEY_COLS)
    if "target_rainfall_clamped" in rain:
        wide["rainfall_clamped"] = rain["target_rainfall_clamped"].reindex(wide.index).astype(bool)
    per_row = long[long["variable"] == VARIABLES[0]].set_index(KEY_COLS)[id_cols + static_cols]
    wide = wide.join(per_row)
    return wide.reset_index()


def load_stage4_wide() -> pd.DataFrame:
    parts = []
    for a in load_json(DATASET_MANIFEST)["dataset_files"]:
        long = pq.read_table(REPO / a["file"], columns=LONG_COLS).to_pandas()
        parts.append(_widen(long, STATIC_FEATURES + STATIC_EXTRA, ID_COLS))
        del long
    wide = pd.concat(parts, ignore_index=True)
    for c in ID_COLS + ["panchayat_lgd_code"]:
        wide[c] = wide[c].astype("category")
    tf = time_features(wide["timestamp_utc"])
    for c in tf.columns:
        wide[c] = tf[c].to_numpy()
    assert all(f in wide.columns for f in COARSE_FEATURES)
    return wide


def load_yelandur_reference_wide() -> pd.DataFrame:
    """Phase 2D Yelandur, PRIMARY population (COMPLETE GPs) only, read-only."""
    cols = KEY_COLS + ["gp_name", "cell_group_id", "in_primary_population", "variable", "target_value",
                       "coarse_bilinear_value", "coarse_nearest_value", "target_rainfall_clamped"] + STATIC_FEATURES + \
        ["coarse_nearest_distance_km"]
    long = pq.read_table(PHASE2D_PARQUET, columns=cols).to_pandas()
    long = long[long["in_primary_population"]]
    long["temporal_period"] = np.where(long["timestamp_utc"] >= pd.Timestamp("2023-01-01", tz="UTC"), "test_period",
                                       np.where(long["timestamp_utc"] >= pd.Timestamp("2022-12-25", tz="UTC"),
                                                "embargo", "train_period"))
    wide = _widen(long, STATIC_FEATURES + STATIC_EXTRA, ["gp_name", "cell_group_id", "temporal_period"])
    tf = time_features(wide["timestamp_utc"])
    for c in tf.columns:
        wide[c] = tf[c].to_numpy()
    return wide
