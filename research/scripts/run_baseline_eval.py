"""
Phase 2A step: offline baseline evaluation against the ERA5-Land proxy
target. Computes REAL MAE/RMSE from data/training/training_pairs.csv  -  if
that file doesn't exist or is empty, this prints that explicitly and exits
non-zero. It never invents a number.

This is a read-only, offline research script. It does not call, import the
routes of, or modify backend/app/downscaling/routes.py or service.py  -  the
live API is untouched.

Usage:
    python research/scripts/run_baseline_eval.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

RESEARCH_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH_DIR))

from pipeline.baseline_eval import (  # noqa: E402
    evaluate_block_as_is,
    evaluate_elevation_temperature_baseline,
)

TRAINING_PAIRS_PATH = RESEARCH_DIR.parent / "data" / "training" / "training_pairs.csv"
EVALUATION_DIR = RESEARCH_DIR.parent / "data" / "evaluation"


def main() -> int:
    if not TRAINING_PAIRS_PATH.exists():
        print(f"BLOCKED  -  no training-pair dataset at {TRAINING_PAIRS_PATH}")
        print("Run run_pilot_acquisition.py -> run_normalize.py -> run_build_training_pairs.py first.")
        return 1

    pairs = pd.read_csv(TRAINING_PAIRS_PATH)
    if pairs.empty:
        print(f"INSUFFICIENT DATA  -  {TRAINING_PAIRS_PATH} exists but contains 0 rows.")
        print("No MAE/RMSE can be computed. This is not a bug  -  it means the acquisition/")
        print("normalization steps upstream have not yet produced any real paired data.")
        return 1

    print(f"Loaded {len(pairs)} training-pair rows from {TRAINING_PAIRS_PATH}")
    print("=" * 60)

    block_as_is = evaluate_block_as_is(pairs)
    elevation_temp = evaluate_elevation_temperature_baseline(pairs)

    print("\nBlock-value-as-is baseline (per variable):")
    for variable, metrics in block_as_is.items():
        print(f"  {variable:<25} {metrics}")

    print("\nPhase 1 elevation-based temperature correction (temperature_c only):")
    for variable, metrics in elevation_temp.items():
        print(f"  {variable:<25} {metrics}")

    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVALUATION_DIR / "baseline_metrics.json"
    with open(out_path, "w") as f:
        json.dump({
            "block_as_is": block_as_is,
            "elevation_temperature_baseline": elevation_temp,
            "note": "Computed against ERA5-Land reanalysis-proxy targets, not observations. "
                    "See research/README.md.",
        }, f, indent=2, default=str)
    print(f"\nWritten: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
