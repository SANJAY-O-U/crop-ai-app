"""
Builds the Yelandur historical village-union spatial proxy layer
(research/spatial_proxy/yelandur_spatial_proxy.json) from the raw LGD +
DataMeet sources fetched by acquire.py.

TERMINOLOGY (per the Stage 6 GO decision -- enforced, not just documented):
this layer is a "historical village-union spatial proxy" / "1991-vintage
spatial proxy derived from village polygons". It is never a present-day
administrative boundary. See PROXY_LABEL / VINTAGE_LABEL below -- every
prose field in the output is built from these constants so the wording
can't drift, and test_spatial_proxy.py greps the committed output for the
disallowed phrasing to guard against regressions.

Source chain, exactly as validated in the Stage 6 feasibility test:

    LGD current GP
    -> official LGD GP->village mapping        (villages_by_blocks.csv)
    -> LGD Census-2001 village code              (villages.csv)
    -> DataMeet V_CT_CODE (exact crosswalk)      (ka.geojson properties)
    -> DataMeet 1991-vintage village polygon     (ka.geojson geometry)

Only code-based matching is used (see matching.py) -- no fuzzy matching
anywhere in this pipeline.
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import pyproj
import shapely.geometry as sgeom
from shapely.ops import transform, unary_union

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from spatial_proxy.acquire import acquire_all  # noqa: E402
from spatial_proxy.matching import match_all_villages  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent / "yelandur_spatial_proxy.json"

# --- fixed, independently-verified LGD identity for this scope ---
STATE_LGD_CODE = "29"                 # Karnataka
DISTRICT_LGD_CODE = "486"             # Zila Panchayat "Chamarajanagar" (pri_local_bodies tier)
TALUKA_PANCHAYAT_LGD_CODE = "6132"    # Taluka Panchayat "Yelandur", parent=486
SUBDISTRICT_CODE = "5578"             # villages.csv / villages_by_blocks.csv "Yelandur" subdistrict
STATE_NAME = "Karnataka"

EXPECTED_GP_COUNT = 12
EXPECTED_VILLAGE_COUNT = 28
EXPECTED_MATCHED_COUNT = 26
EXPECTED_COMPLETE = 10
EXPECTED_PARTIAL = 1
EXPECTED_UNAVAILABLE = 1

PROXY_LABEL = "historical village-union spatial proxy"
VINTAGE_LABEL = "1991-vintage spatial proxy derived from village polygons"

SOURCE_LICENSE = (
    "Open Data Commons Open Database License (ODbL) v1.0 -- "
    "datameet/indian_village_boundaries. Attribution required (DataMeet "
    "project; original digitization by CISED, now merged with ATREE). "
    "Share-alike: a redistributed derivative database must itself be "
    "offered under ODbL or a compatible license; 'produced works' "
    "(rendered maps, aggregate statistics) may use different terms."
)
SOURCE_POSITIONAL_ERROR = (
    "+/-500m (per source project documentation, docs/ka/index.html: "
    "digitized manually from District Census Handbooks of Census 1991, "
    "geo-rectified against Survey of India toposheets)"
)
SOURCE_CRS_NOTE = (
    "WGS84 geographic (EPSG:4326-equivalent decimal degrees). NOT declared "
    "via an explicit GeoJSON 'crs' member in the source file -- this is the "
    "RFC 7946 default for an undeclared CRS, corroborated by the source "
    "project's own documentation (docs/ka/index.html: 'reprojected to "
    "WGS84 datum and Geographic projection, units: decimal degrees')."
)
CENTROID_AREA_CRS = "EPSG:32643 (UTM Zone 43N) -- used only for centroid/area math, not for stored geometry"

_transformer_to_utm = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True).transform
_transformer_to_wgs84 = pyproj.Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True).transform


def load_lgd_villages(lgd_paths: dict) -> list[dict]:
    with open(lgd_paths["villages"], encoding="utf-8") as f:
        village_rows = [
            r for r in csv.DictReader(f)
            if r["State Name(In English)"].strip() == STATE_NAME
            and r["Sub-District Code"] == SUBDISTRICT_CODE
        ]
    with open(lgd_paths["villages_by_blocks"], encoding="utf-8") as f:
        vbb_rows = [
            r for r in csv.DictReader(f)
            if r["State Name (In English)"].strip() == STATE_NAME
            and r["Subdistrict Code"] == SUBDISTRICT_CODE
        ]

    if len(village_rows) != EXPECTED_VILLAGE_COUNT or len(vbb_rows) != EXPECTED_VILLAGE_COUNT:
        raise RuntimeError(
            f"STOP: expected {EXPECTED_VILLAGE_COUNT} LGD villages under Yelandur "
            f"(subdistrict {SUBDISTRICT_CODE}), got villages.csv={len(village_rows)} "
            f"villages_by_blocks.csv={len(vbb_rows)}. Downloaded data no longer "
            f"matches the Stage 6 feasibility result -- do not silently adapt."
        )

    vbb_by_code = {r["Village Code"]: r for r in vbb_rows}
    villages = []
    for r in village_rows:
        vcode = r["Village Code"]
        vbb = vbb_by_code[vcode]
        villages.append({
            "village_name": r["Village Name (In English)"],
            "village_lgd_code": vcode,
            "census_2001_code": r["Census 2001 Code"],
            "census_2011_code": r["Census 2011 Code"],
            "gp_name": vbb["Local Body Name (In English)"],
            "gp_lgd_code": vbb["Local Body Code"],
        })
    return villages


def load_official_gp_roster(lgd_paths: dict) -> dict[str, str]:
    """Returns {gp_lgd_code: gp_name} for the 12 Gram Panchayats whose
    parent is Taluka Panchayat 6132 (Yelandur), read directly from
    pri_local_bodies.csv -- independent of the village-level join, so a
    village-table bug can't silently hide a missing/extra GP."""
    with open(lgd_paths["pri_local_bodies"], encoding="utf-8") as f:
        rows = [
            r for r in csv.DictReader(f)
            if r["State Name"].strip() == STATE_NAME
            and r["Localbody Type Code"] == "3"
            and r["Parent Localbody Code"] == TALUKA_PANCHAYAT_LGD_CODE
        ]
    if len(rows) != EXPECTED_GP_COUNT:
        raise RuntimeError(
            f"STOP: expected {EXPECTED_GP_COUNT} Gram Panchayats under Taluka "
            f"Panchayat {TALUKA_PANCHAYAT_LGD_CODE}, got {len(rows)}."
        )
    return {r["Localbody Code"]: r["Localbody Name (In English)"] for r in rows}


def load_datameet_yelandur_features(geojson_path: Path) -> list[dict]:
    with open(geojson_path, encoding="utf-8") as f:
        data = json.load(f)
    return [
        ft for ft in data["features"]
        if (ft["properties"].get("DISTRICT") or "").strip() == "Chamarajnagar"
        and (ft["properties"].get("TALUK") or "").strip() == "Yelandur"
    ]


def _validate_geometry(geom, label: str):
    if not geom.is_valid:
        raise RuntimeError(
            f"STOP: invalid geometry for {label} (shapely reason: "
            f"{shapely_explain(geom)}). Not silently repairing -- report this."
        )


def shapely_explain(geom) -> str:
    from shapely.validation import explain_validity
    return explain_validity(geom)


def build_gp_record(gp_lgd_code: str, gp_name: str, matches: list, manifest: dict) -> dict:
    matched = [m for m in matches if m.dm_feature is not None]
    missing = [m.village_name for m in matches if m.dm_feature is None]
    expected = len(matches)
    n_matched = len(matched)

    if n_matched == 0:
        status = "UNAVAILABLE"
    elif n_matched == expected:
        status = "COMPLETE"
    else:
        status = "PARTIAL"

    for m in matched:
        geom = sgeom.shape(m.dm_feature["geometry"])
        _validate_geometry(geom, f"source village '{m.village_name}'")

    geometry = None
    centroid_wgs84 = None
    area_km2 = None
    union_geom_type = None

    if status != "UNAVAILABLE":
        village_geoms = [sgeom.shape(m.dm_feature["geometry"]) for m in matched]
        union_geom = unary_union(village_geoms)
        _validate_geometry(union_geom, f"GP union '{gp_name}'")

        union_geom_type = union_geom.geom_type
        union_utm = transform(_transformer_to_utm, union_geom)
        centroid_utm = union_utm.centroid
        centroid_wgs = transform(_transformer_to_wgs84, centroid_utm)
        centroid_wgs84 = {"lon": centroid_wgs.x, "lat": centroid_wgs.y}
        area_km2 = union_utm.area / 1_000_000
        geometry = sgeom.mapping(union_geom)

    if status == "COMPLETE":
        geometry_basis = f"{PROXY_LABEL} ({VINTAGE_LABEL}); {n_matched}/{expected} constituent villages matched"
    elif status == "PARTIAL":
        geometry_basis = (
            f"{PROXY_LABEL} ({VINTAGE_LABEL}); PARTIAL union of {n_matched}/{expected} "
            f"constituent villages -- missing village(s) {missing} excluded entirely, "
            f"union UNDERSTATES the true historical extent"
        )
    else:
        geometry_basis = (
            f"no {PROXY_LABEL} could be built -- 0/{expected} constituent village(s) "
            f"have a matched DataMeet polygon; missing: {missing}"
        )

    return {
        "state_lgd_code": STATE_LGD_CODE,
        "district_lgd_code": DISTRICT_LGD_CODE,
        "taluka_panchayat_lgd_code": TALUKA_PANCHAYAT_LGD_CODE,
        "panchayat_lgd_code": gp_lgd_code,
        "panchayat_name": gp_name,
        "expected_village_count": expected,
        "matched_village_count": n_matched,
        "missing_village_count": expected - n_matched,
        "missing_villages": missing,
        "geometry_status": status,
        "geometry_source": "datameet/indian_village_boundaries, ka/ka.geojson",
        "geometry_vintage": VINTAGE_LABEL,
        "geometry_basis": geometry_basis,
        "source_license": SOURCE_LICENSE,
        "source_positional_error": SOURCE_POSITIONAL_ERROR,
        "source_crs": SOURCE_CRS_NOTE,
        "source_blob_sha": manifest["blob_sha"],
        "source_content_commit": manifest["last_content_commit_sha"],
        "source_note": (
            f"This is a {PROXY_LABEL}, not a present-day Panchayat boundary. "
            f"Constituent villages matched via exact Census-2001-code crosswalk "
            f"only (no fuzzy or name-only matching used for any of the "
            f"{n_matched} matched villages here)."
        ),
        "constituent_villages": [
            {
                "village_name": m.village_name,
                "village_lgd_code": m.village_lgd_code,
                "census_2001_code": m.census_2001_code,
                "census_2011_code": m.census_2011_code,
                "match_method": m.method,
                "matched": m.dm_feature is not None,
            }
            for m in matches
        ],
        "projected_crs_used_for_centroid_area": CENTROID_AREA_CRS if status != "UNAVAILABLE" else None,
        "centroid_wgs84": centroid_wgs84,
        "area_km2": area_km2,
        "union_geometry_type": union_geom_type,
        "geometry": geometry,
    }


def build() -> dict:
    sources = acquire_all()
    lgd_paths = sources["lgd"]
    manifest = sources["datameet_manifest"]

    lgd_villages = load_lgd_villages(lgd_paths)
    gp_roster = load_official_gp_roster(lgd_paths)
    dm_features = load_datameet_yelandur_features(sources["datameet_geojson"])

    matches = match_all_villages(lgd_villages, dm_features)

    matches_by_gp = defaultdict(list)
    for m in matches:
        matches_by_gp[m.gp_lgd_code].append(m)

    if set(matches_by_gp.keys()) != set(gp_roster.keys()):
        raise RuntimeError(
            "STOP: village->GP join produced a different GP set than the "
            f"official pri_local_bodies roster. Roster={gp_roster.keys()} "
            f"Joined={matches_by_gp.keys()}"
        )

    gp_records = [
        build_gp_record(gp_code, gp_roster[gp_code], matches_by_gp[gp_code], manifest)
        for gp_code in gp_roster
    ]
    gp_records.sort(key=lambda r: r["panchayat_name"])

    n_matched_total = sum(1 for m in matches if m.dm_feature is not None)
    n_complete = sum(1 for r in gp_records if r["geometry_status"] == "COMPLETE")
    n_partial = sum(1 for r in gp_records if r["geometry_status"] == "PARTIAL")
    n_unavailable = sum(1 for r in gp_records if r["geometry_status"] == "UNAVAILABLE")

    actual = (n_matched_total, n_complete, n_partial, n_unavailable)
    expected = (EXPECTED_MATCHED_COUNT, EXPECTED_COMPLETE, EXPECTED_PARTIAL, EXPECTED_UNAVAILABLE)
    if actual != expected:
        raise RuntimeError(
            "STOP: matching/coverage result diverged from the Stage 6 feasibility "
            f"finding. Expected (matched, complete, partial, unavailable)={expected}, "
            f"got {actual}. Reporting discrepancy instead of silently adapting -- "
            f"inspect the GP records below before trusting this output.\n"
            f"{json.dumps(gp_records, indent=2, default=str)}"
        )

    non_fuzzy_methods = {"EXACT_CODE", "EXACT_CROSSWALK", "EXACT_NAME", "UNMATCHED"}
    for m in matches:
        if m.method not in non_fuzzy_methods:
            raise RuntimeError(f"STOP: unexpected/ambiguous match method '{m.method}' for {m.village_name}")

    layer = {
        "type": "YelandurSpatialProxyLayer",
        "label": PROXY_LABEL,
        "vintage": VINTAGE_LABEL,
        "terminology_note": (
            "Every geometry in this layer is a research-only spatial proxy "
            "reconstructed from 1991-vintage village polygons. It must never "
            "be interpreted as a present-day, in-force administrative "
            "boundary of any kind."
        ),
        "scope": {
            "state_name": STATE_NAME,
            "state_lgd_code": STATE_LGD_CODE,
            "district_lgd_code": DISTRICT_LGD_CODE,
            "taluka_panchayat_lgd_code": TALUKA_PANCHAYAT_LGD_CODE,
            "subdistrict_code": SUBDISTRICT_CODE,
        },
        "source_chain": [
            "LGD current GP",
            "official LGD GP->village mapping (villages_by_blocks.csv)",
            "LGD Census-2001 village code (villages.csv)",
            "DataMeet V_CT_CODE (exact crosswalk)",
            "DataMeet 1991-vintage village polygon (ka.geojson geometry)",
        ],
        "matching_methodology": (
            "Code-based only: DataMeet's V_CT_CODE, zero-padded to 8 digits, "
            "compared for exact equality against LGD's own Census-2001 Code "
            "for the same village. No fuzzy matching, no name-similarity "
            "matching, and no headquarters-village shortcuts were used. GP "
            "membership taken only from the official LGD village->GP mapping."
        ),
        "coverage_summary": {
            "expected_gp_count": EXPECTED_GP_COUNT,
            "expected_village_count": EXPECTED_VILLAGE_COUNT,
            "matched_village_count": n_matched_total,
            "complete_gp_count": n_complete,
            "partial_gp_count": n_partial,
            "unavailable_gp_count": n_unavailable,
        },
        "source_provenance": {
            "datameet_repo": manifest["repo"],
            "datameet_path": manifest["path"],
            "datameet_blob_sha": manifest["blob_sha"],
            "datameet_content_commit": manifest["last_content_commit_sha"],
            "datameet_content_commit_date": manifest["last_content_commit_date"],
            "datameet_license": SOURCE_LICENSE,
            "lgd_release_tag": "lgd-latest-extra1",
            "lgd_mirror_repo": "ramSeraph/opendata",
            "lgd_origin": "https://lgdirectory.gov.in (Ministry of Panchayati Raj)",
        },
        "panchayats": gp_records,
    }
    return layer


if __name__ == "__main__":
    layer = build()
    OUTPUT_PATH.write_text(json.dumps(layer, indent=2), encoding="utf-8")
    summary = layer["coverage_summary"]
    print(f"Wrote {OUTPUT_PATH}")
    print(f"Coverage: {summary}")
