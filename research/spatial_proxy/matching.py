"""
Village-level matching between LGD's official Yelandur village->GP mapping
and DataMeet's 1991-vintage Karnataka village polygons.

Matching hierarchy (validated in the Stage 6 feasibility test, see
research/spatial_proxy/README.md):

  EXACT_CODE       -- DataMeet exposes LGD's own Census-2011 village code
                       directly. Structurally unavailable for this dataset:
                       ka.geojson's native properties carry no Census-2011
                       field at all (only 1991/2001-era identifiers).
  EXACT_CROSSWALK  -- DataMeet's V_CT_CODE property, zero-padded to 8
                       digits, matches LGD's own "Census 2001 Code" column
                       for the same village row exactly. LGD independently
                       records both the 2001 and current 2011 codes per
                       village, so this chains to a real Census-2011/LGD
                       village code without ever comparing names.
  EXACT_NAME       -- fallback only: normalized (uppercase, alnum-only)
                       name equality. Never used if a code match exists.
  AMBIGUOUS        -- more than one DataMeet feature matches.
  UNMATCHED        -- no DataMeet feature matches by code or exact name.

No fuzzy matching is implemented anywhere in this module -- there is no
similarity threshold, edit-distance check, or partial-string logic.
"""

import re
from dataclasses import dataclass


def normalize_name(name: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (name or "").upper())


@dataclass
class VillageMatch:
    village_name: str
    village_lgd_code: str
    census_2001_code: str
    census_2011_code: str
    gp_name: str
    gp_lgd_code: str
    method: str  # EXACT_CODE | EXACT_CROSSWALK | EXACT_NAME | AMBIGUOUS | UNMATCHED
    dm_feature: dict | None  # the matched DataMeet GeoJSON feature, or None


def index_datameet_features_by_vct_code(features: list[dict]) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for ft in features:
        vct = (ft["properties"].get("V_CT_CODE") or "").strip()
        if vct:
            index.setdefault(vct, []).append(ft)
    return index


def index_datameet_features_by_normalized_name(features: list[dict]) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for ft in features:
        for field in ("NAME", "VILL_NAME"):
            n = normalize_name(ft["properties"].get(field))
            if n:
                index.setdefault(n, []).append(ft)
    return index


def match_village(
    lgd_village: dict,
    by_vct_code: dict[str, list[dict]],
    by_norm_name: dict[str, list[dict]],
) -> VillageMatch:
    """Matches one official LGD village row against the indexed DataMeet
    Yelandur-taluk features, following the code-first hierarchy above."""
    c2001 = (lgd_village["census_2001_code"] or "").strip()
    vct_key = c2001.zfill(8) if c2001 else ""

    matched_features: list[dict] = []
    method = "UNMATCHED"

    if vct_key and vct_key in by_vct_code:
        matched_features = by_vct_code[vct_key]
        method = "EXACT_CROSSWALK"
    else:
        nname = normalize_name(lgd_village["village_name"])
        if nname in by_norm_name:
            matched_features = by_norm_name[nname]
            method = "EXACT_NAME"

    if len(matched_features) > 1:
        method = "AMBIGUOUS"

    return VillageMatch(
        village_name=lgd_village["village_name"],
        village_lgd_code=lgd_village["village_lgd_code"],
        census_2001_code=lgd_village["census_2001_code"],
        census_2011_code=lgd_village["census_2011_code"],
        gp_name=lgd_village["gp_name"],
        gp_lgd_code=lgd_village["gp_lgd_code"],
        method=method,
        dm_feature=matched_features[0] if len(matched_features) == 1 else None,
    )


def match_all_villages(
    lgd_villages: list[dict],
    dm_yelandur_features: list[dict],
) -> list[VillageMatch]:
    by_vct_code = index_datameet_features_by_vct_code(dm_yelandur_features)
    by_norm_name = index_datameet_features_by_normalized_name(dm_yelandur_features)
    return [match_village(v, by_vct_code, by_norm_name) for v in lgd_villages]
