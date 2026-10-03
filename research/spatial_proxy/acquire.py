"""
Reproducible fetch of the two REAL source datasets this Stage 6 spatial
proxy layer is built from:

  1. LGD village-level components (villages, villages_by_blocks,
     subdistricts, pri_local_bodies, states) -- same ramSeraph/opendata
     mirror used by research/admin_identity/fetch_lgd_identity.py.
  2. DataMeet's Karnataka 1991-vintage village boundary layer
     (datameet/indian_village_boundaries, ka/ka.geojson) -- an 86MB file
     that is deliberately NEVER committed to this repository. It is cached
     under data/raw/datameet/ (gitignored via the existing `data/raw/**`
     rule) and re-downloaded only if missing.

This module only downloads and caches raw source files. It does not match,
dissolve, or otherwise interpret them -- see matching.py and build.py.
"""

import json
import urllib.request
from pathlib import Path

import py7zr

REPO_ROOT = Path(__file__).resolve().parents[2]
LGD_RAW_DIR = REPO_ROOT / "data" / "raw" / "lgd"
DATAMEET_RAW_DIR = REPO_ROOT / "data" / "raw" / "datameet"

# --- LGD (ramSeraph/opendata mirror of lgdirectory.gov.in) ---
LGD_REPO = "ramSeraph/opendata"
LGD_RELEASE_TAG = "lgd-latest-extra1"
# NOTE: villages / villages_by_blocks are only available through 31Jul2026 on
# this mirror as of this writing -- a later date silently 404s. Recorded
# here rather than assumed, same discipline as fetch_lgd_identity.py.
LGD_COMPONENT_DATES = {
    "states": "22Sep2026",
    "districts": "22Sep2026",
    "pri_local_bodies": "22Sep2026",
    "subdistricts": "22Sep2026",
    "villages": "31Jul2026",
    "villages_by_blocks": "31Jul2026",
}

# --- DataMeet (datameet/indian_village_boundaries, ODbL 1.0) ---
DATAMEET_REPO = "datameet/indian_village_boundaries"
DATAMEET_RAW_URL = (
    f"https://raw.githubusercontent.com/{DATAMEET_REPO}/master/ka/ka.geojson"
)
DATAMEET_API_CONTENTS_URL = (
    f"https://api.github.com/repos/{DATAMEET_REPO}/contents/ka/ka.geojson?ref=master"
)
DATAMEET_API_COMMITS_URL = (
    f"https://api.github.com/repos/{DATAMEET_REPO}/commits?path=ka/ka.geojson&per_page=1"
)


def _lgd_asset_url(component: str) -> str:
    date = LGD_COMPONENT_DATES[component]
    return (
        f"https://github.com/{LGD_REPO}/releases/download/{LGD_RELEASE_TAG}/"
        f"{component}.{date}.csv.7z"
    )


def fetch_lgd_component(component: str) -> Path:
    """Downloads + extracts one LGD component's .7z release asset into
    data/raw/lgd/ (gitignored). Returns the extracted CSV path. Raises on
    any HTTP/extraction failure -- never fabricates a result."""
    LGD_RAW_DIR.mkdir(parents=True, exist_ok=True)
    date = LGD_COMPONENT_DATES[component]
    archive_path = LGD_RAW_DIR / f"{component}.{date}.csv.7z"
    csv_path = LGD_RAW_DIR / f"{component}.{date}.csv"

    if not csv_path.exists():
        with urllib.request.urlopen(_lgd_asset_url(component), timeout=120) as resp:
            archive_path.write_bytes(resp.read())
        with py7zr.SevenZipFile(archive_path, mode="r") as archive:
            archive.extractall(path=LGD_RAW_DIR)

    return csv_path


def fetch_datameet_karnataka() -> Path:
    """Downloads DataMeet's Karnataka village boundary GeoJSON (~86MB) into
    data/raw/datameet/ka.geojson (gitignored). Never committed, per the
    Stage 6 instruction not to redistribute the raw source file in this
    repository. Idempotent -- skips the download if already cached."""
    DATAMEET_RAW_DIR.mkdir(parents=True, exist_ok=True)
    geojson_path = DATAMEET_RAW_DIR / "ka.geojson"

    if not geojson_path.exists():
        with urllib.request.urlopen(DATAMEET_RAW_URL, timeout=300) as resp:
            geojson_path.write_bytes(resp.read())

    return geojson_path


def fetch_datameet_provenance_manifest() -> dict:
    """Fetches (from the GitHub API, real HTTP, no auth needed for public
    repos) the exact blob SHA and last content-commit for ka.geojson, and
    caches them to data/raw/datameet/provenance_manifest.json so build.py
    can embed them in the committed output without needing network access
    on every build. Raises on failure rather than fabricating identifiers."""
    DATAMEET_RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = DATAMEET_RAW_DIR / "provenance_manifest.json"

    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    with urllib.request.urlopen(DATAMEET_API_CONTENTS_URL, timeout=30) as resp:
        contents = json.loads(resp.read())
    with urllib.request.urlopen(DATAMEET_API_COMMITS_URL, timeout=30) as resp:
        commits = json.loads(resp.read())

    manifest = {
        "repo": DATAMEET_REPO,
        "path": "ka/ka.geojson",
        "raw_url": DATAMEET_RAW_URL,
        "blob_sha": contents["sha"],
        "file_size_bytes": contents["size"],
        "last_content_commit_sha": commits[0]["sha"],
        "last_content_commit_date": commits[0]["commit"]["committer"]["date"],
        "last_content_commit_message": commits[0]["commit"]["message"],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def acquire_all() -> dict:
    """Fetches every raw source this layer depends on. Returns a dict of
    component name -> local path (LGD CSVs) plus the DataMeet geojson path
    and provenance manifest. Called by build.py; also runnable standalone
    for cache warming."""
    lgd_paths = {c: fetch_lgd_component(c) for c in LGD_COMPONENT_DATES}
    datameet_path = fetch_datameet_karnataka()
    datameet_manifest = fetch_datameet_provenance_manifest()
    return {
        "lgd": lgd_paths,
        "datameet_geojson": datameet_path,
        "datameet_manifest": datameet_manifest,
    }


if __name__ == "__main__":
    result = acquire_all()
    print("LGD components cached at:")
    for name, path in result["lgd"].items():
        print(f"  {name}: {path}")
    print(f"DataMeet geojson cached at: {result['datameet_geojson']}")
    print(f"DataMeet provenance: {result['datameet_manifest']}")
