"""
CLI entry point for Phase 2A step 1: prove ERA5-Land authentication + a
small historical request actually work.

Usage:
    python research/scripts/run_pilot_acquisition.py

This makes a REAL network call if credentials are configured. It never
fabricates a "success"  -  a missing-credentials or request failure is
printed exactly as raised, with the manual action required to fix it.
"""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # research/

from config import MissingCredentialsError  # noqa: E402
from era5_land.acquire import download_pilot  # noqa: E402


def main() -> int:
    print("CropCast Phase 2A  -  ERA5-Land pilot acquisition")
    print("=" * 60)
    try:
        path = download_pilot()
    except MissingCredentialsError as exc:
        print("\nBLOCKED  -  no Copernicus CDS credentials configured.\n")
        print(str(exc))
        print(
            "\nManual action required (cannot be automated):\n"
            "  1. Create a free account at https://cds.climate.copernicus.eu\n"
            "  2. Log in, open https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land\n"
            "     and accept that dataset's Terms of Use (one-time, must be done in-browser)\n"
            "  3. Copy your Personal Access Token from https://cds.climate.copernicus.eu/profile\n"
            "  4. Set it as an environment variable:\n"
            "       export CDSAPI_KEY=<your-token>\n"
            "     (or write $HOME/.cdsapirc  -  see research/README.md)\n"
            "  5. Re-run this script.\n"
        )
        return 1
    except Exception:
        print("\nFAILED  -  the request reached the CDS client but did not succeed.")
        print("This usually means: Terms of Use not yet accepted for this dataset,")
        print("an invalid/expired token, or a network problem. Full error below:\n")
        traceback.print_exc()
        return 1

    print(f"\nSUCCESS  -  downloaded to: {path}")
    print("Next: python research/scripts/run_normalize.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
