"""
Pilot-location registry for the archive. Nothing here invents geography:

  live_demo_pilot    the block and 3 Panchayats of the LIVE CropCastAI seed data (backend/app/geospatial/seed_data.py),
                     all is_demo_data=True (placeholder identities near Nandi Hills).
  yelandur_research  the block proxy and 10 primary Gram Panchayats of the frozen Phase 2D research dataset (real LGD
                     identities; geometry = 1991 village-union proxy centroids). Its block point is the mean of those
                     10 centroids -- a research-defined point, not an official block centroid.

The registry JSON is written once by `python research/forecast_archive/locations.py --write` and committed, so a
collection run depends only on that small file.
"""

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
REGISTRY_PATH = _HERE / "location_registry.json"
LIVE, YELANDUR = "live_demo_pilot", "yelandur_research"
# location_role says WHAT THE GEOGRAPHY IS USED FOR; is_demo_data says whether the identity is placeholder data. They differ:
#   live_demo_pilot     the geography of the live CropCastAI demo (placeholder identities, is_demo_data=true)
#   research_validation offline research/evaluation geography only -- NOT the live CropCastAI demo geography
#                       (real LGD identities, is_demo_data=false)
ROLE_LIVE, ROLE_RESEARCH = "live_demo_pilot", "research_validation"


def era5_land_cell(lat: float, lon: float) -> str:
    """Nearest 0.1 deg ERA5-Land cell centre (same rule as the Stage 4 grid)."""
    return f"E5L_{round(lat * 10) / 10:.2f}N_{round(lon * 10) / 10:.2f}E"


def build_registry() -> dict:
    sys.path.insert(0, str(_ROOT / "backend"))
    from app.geospatial.seed_data import DEMO_BLOCK, DEMO_PANCHAYATS  # the live seed data, not a copy

    locs = [{"location_id": DEMO_BLOCK.block_id, "location_set": LIVE, "location_role": ROLE_LIVE, "role": "block", "block_id": DEMO_BLOCK.block_id,
             "panchayat_id": None, "name": DEMO_BLOCK.block_name, "latitude": DEMO_BLOCK.latitude,
             "longitude": DEMO_BLOCK.longitude, "elevation_m": DEMO_BLOCK.elevation_m, "is_demo_data": DEMO_BLOCK.is_demo_data,
             "era5_land_cell": era5_land_cell(DEMO_BLOCK.latitude, DEMO_BLOCK.longitude), "source": "backend/app/geospatial/seed_data.py"}]
    for p in DEMO_PANCHAYATS:
        locs.append({"location_id": p.panchayat_id, "location_set": LIVE, "location_role": ROLE_LIVE, "role": "panchayat", "block_id": p.block_id,
                     "panchayat_id": p.panchayat_id, "name": p.panchayat_name, "latitude": p.latitude, "longitude": p.longitude,
                     "elevation_m": p.elevation_m, "is_demo_data": p.is_demo_data,
                     "era5_land_cell": era5_land_cell(p.latitude, p.longitude), "source": "backend/app/geospatial/seed_data.py"})

    import pandas as pd
    cols = ["gp_name", "panchayat_lgd_code", "cell_group_id", "coverage_status", "in_primary_population",
            "centroid_latitude", "centroid_longitude", "elevation_mean_m"]
    d = pd.read_parquet(_ROOT / "data/training/yelandur_multi_gp.parquet", columns=cols)
    d = d[d["in_primary_population"] & (d["coverage_status"] == "COMPLETE")].drop_duplicates("gp_name").sort_values("gp_name")
    block_id = "YELANDUR-BLOCK-PROXY"
    lat_m, lon_m = float(d["centroid_latitude"].mean()), float(d["centroid_longitude"].mean())
    locs.append({"location_id": block_id, "location_set": YELANDUR, "location_role": ROLE_RESEARCH, "role": "block", "block_id": block_id, "panchayat_id": None,
                 "name": "Yelandur (research block point = mean of 10 GP centroids)", "latitude": round(lat_m, 6),
                 "longitude": round(lon_m, 6), "elevation_m": round(float(d["elevation_mean_m"].mean()), 1),
                 "is_demo_data": False, "era5_land_cell": era5_land_cell(lat_m, lon_m),
                 "source": "data/training/yelandur_multi_gp.parquet (derived)"})
    for _, r in d.iterrows():
        pid = f"LGD-{r['panchayat_lgd_code']}"
        locs.append({"location_id": pid, "location_set": YELANDUR, "location_role": ROLE_RESEARCH, "role": "panchayat", "block_id": block_id, "panchayat_id": pid,
                     "name": r["gp_name"], "latitude": round(float(r["centroid_latitude"]), 6), "longitude": round(float(r["centroid_longitude"]), 6),
                     "elevation_m": round(float(r["elevation_mean_m"]), 1), "is_demo_data": False, "era5_land_cell": r["cell_group_id"],
                     "source": "data/training/yelandur_multi_gp.parquet", "geometry_note": "1991 village-union proxy centroid; elevation = GLO-30 zonal mean"})
    return {"registry_version": 1, "note": "Block rows are the forecast INPUT locations; Panchayat rows are TARGET locations (never forecast sources here).",
            "locations": locs}


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def block_locations(registry: dict, sets=None) -> list[dict]:
    return [l for l in registry["locations"] if l["role"] == "block" and (not sets or l["location_set"] in sets)]


def panchayats_of(registry: dict, block_id: str) -> list[dict]:
    return [l for l in registry["locations"] if l["role"] == "panchayat" and l["block_id"] == block_id]


def spatial_groups(registry: dict, location_set: str) -> int:
    """Number of distinct ERA5-Land cells among a set's Panchayats = independent spatial units for evaluation."""
    return len({l["era5_land_cell"] for l in registry["locations"] if l["location_set"] == location_set and l["role"] == "panchayat"})


if __name__ == "__main__":
    if "--write" in sys.argv:
        REGISTRY_PATH.write_text(json.dumps(build_registry(), indent=2), encoding="utf-8")
        print("wrote", REGISTRY_PATH)
    else:
        reg = load_registry()
        for s in (LIVE, YELANDUR):
            print(s, "locations:", sum(l["location_set"] == s for l in reg["locations"]), "spatial groups:", spatial_groups(reg, s))
