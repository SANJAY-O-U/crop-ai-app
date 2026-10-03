"""
Reproducible fetch of REAL Karnataka Panchayat identity data from the
Ministry of Panchayati Raj's Local Government Directory (LGD), via the
ramSeraph/opendata GitHub mirror investigated in Phase 2C.

IDENTITY/METADATA ONLY. This script does not touch, request, or infer any
coordinate, elevation, or geometry. Its output has no spatial meaning and
must never be assumed to correspond to research/pilot_points.py's points or
to any ERA5-Land grid cell.

Why this mirror instead of lgdirectory.gov.in directly: the official portal
gates its downloads behind a CAPTCHA with no documented API (see the
Phase 2C investigation report). ramSeraph/opendata is a community project
that scrapes the SAME official site and republishes it as dated GitHub
Release assets — anonymously downloadable over plain HTTPS (verified this
session: `curl -I` on a release asset URl returns 200 with no auth), which
is what makes this reproducible without a browser/CAPTCHA/manual GUI step.
The data's own origin is still lgdirectory.gov.in; this mirror is a
transport/reproducibility convenience, not a different source of truth.

  Mirror repo:    https://github.com/ramSeraph/opendata
  Release used:   lgd-latest-extra1
  Origin:         https://lgdirectory.gov.in (Ministry of Panchayati Raj)

Components fetched:
  states             - State Code / State Name (LGD)
  districts          - Revenue Department District Code / Name (LGD)
  pri_local_bodies   - the SELF-CONTAINED Panchayati Raj Institution
                        hierarchy: Zilla Parishad (type 1) -> Panchayat
                        Samiti (type 2) -> Gram Panchayat (type 3), joined
                        via Parent Localbody Code WITHIN this one table.
                        In Karnataka these are locally named "Zila
                        Panchayat", "Taluka Panchayat", "Gram Panchayat".

IMPORTANT, VERIFIED DISCREPANCY (see README.md for full detail): LGD's
`districts` table and `pri_local_bodies`' Zilla-Parishad-tier rows are TWO
DIFFERENT CODE NAMESPACES for the same real-world district, and their
names do not always match exactly as strings (verified: districts.csv
spells Karnataka's Bagalkote district "Bagalkote" / code 524; the
pri_local_bodies Zila Panchayat for the same district is spelled "Bagalkot"
/ code 479 — no shared code links them). This script does NOT attempt to
silently reconcile that; it fetches both, uses `pri_local_bodies` as the
single source of truth for the hierarchy actually used (because it is the
only one with code-verified parent/child links all the way down to Gram
Panchayat), and records the districts.csv row separately for disclosure.

Similarly, LGD's `blocks` table ("Development Block") is a SEPARATE entity
type from `pri_local_bodies`' Panchayat-Samiti tier, not code-linked to it.
This script does not fetch `blocks.csv` at all, specifically to avoid
implying a join that was never verified.
"""

import csv
import io
import urllib.request
from pathlib import Path

import py7zr

REPO = "ramSeraph/opendata"
RELEASE_TAG = "lgd-latest-extra1"
ASSET_DATE = "22Sep2026"  # retrieval date this Stage 1 dataset was built from
RETRIEVED_AT = "2026-09-22"

COMPONENTS = ["states", "districts", "pri_local_bodies"]

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "lgd"

TARGET_STATE = "Karnataka"
TARGET_DISTRICT_ZP = "Bagalkot"     # Zila Panchayat name, pri_local_bodies.csv
TARGET_BLOCK_TP = "Guledagudda"     # Taluka Panchayat name, pri_local_bodies.csv


def _asset_url(component: str) -> str:
    return (
        f"https://github.com/{REPO}/releases/download/{RELEASE_TAG}/"
        f"{component}.{ASSET_DATE}.csv.7z"
    )


def download_and_extract(component: str) -> Path:
    """Downloads one component's .7z release asset (anonymous HTTPS, no
    auth/CAPTCHA/GUI) and extracts it into data/raw/lgd/. Returns the
    extracted CSV path. Raises on any HTTP or extraction failure — never
    fabricates a result if the real download didn't succeed."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = RAW_DIR / f"{component}.{ASSET_DATE}.csv.7z"
    csv_path = RAW_DIR / f"{component}.{ASSET_DATE}.csv"

    if not csv_path.exists():
        url = _asset_url(component)
        with urllib.request.urlopen(url, timeout=60) as resp:
            archive_path.write_bytes(resp.read())
        with py7zr.SevenZipFile(archive_path, mode="r") as archive:
            archive.extractall(path=RAW_DIR)

    return csv_path


def load_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_identity_rows() -> list[dict]:
    """
    Fetches the real LGD components and returns the verified Karnataka /
    Bagalkot (Zila Panchayat) / Guledagudda (Taluka Panchayat) Gram
    Panchayat rows — one dict per real Gram Panchayat, with the full
    verified hierarchy attached. Every code/name below is read directly
    from the downloaded files; nothing is invented.
    """
    states = load_csv(download_and_extract("states"))
    districts = load_csv(download_and_extract("districts"))
    pri = load_csv(download_and_extract("pri_local_bodies"))

    state_row = next(r for r in states if r["State Name (In English)"].strip() == TARGET_STATE)
    state_code = state_row["State Code"]

    pri_karnataka = [r for r in pri if r["State Name"].strip() == TARGET_STATE]
    by_code = {r["Localbody Code"]: r for r in pri_karnataka}

    zp_row = next(
        r for r in pri_karnataka
        if r["Localbody Type Code"] == "1" and r["Localbody Name (In English)"].strip() == TARGET_DISTRICT_ZP
    )
    tp_row = next(
        r for r in pri_karnataka
        if r["Localbody Type Code"] == "2"
        and r["Localbody Name (In English)"].strip() == TARGET_BLOCK_TP
        and r["Parent Localbody Code"] == zp_row["Localbody Code"]
    )
    gp_rows = [
        r for r in pri_karnataka
        if r["Localbody Type Code"] == "3" and r["Parent Localbody Code"] == tp_row["Localbody Code"]
    ]
    if not gp_rows:
        raise RuntimeError(
            f"No Gram Panchayats found under Taluka Panchayat "
            f"'{TARGET_BLOCK_TP}' (code {tp_row['Localbody Code']}) — "
            f"target selection is no longer valid against the fetched data."
        )

    # Cross-reference only, for disclosure — NOT used as the code of record.
    revenue_district_row = next(
        (r for r in districts
         if r["State Name (In English)"].strip() == TARGET_STATE
         and r["District Name(In English)"].strip().rstrip("e") == TARGET_DISTRICT_ZP.rstrip("e")),
        None,
    )
    revenue_note = (
        f"districts.csv name-matched candidate: "
        f"{revenue_district_row['District Name(In English)']} "
        f"(District Code {revenue_district_row['District Code']}) — "
        f"NOT code-linked to the Zila Panchayat used here; name match only, "
        f"not asserted as the same code."
        if revenue_district_row else
        "No districts.csv row found even by approximate name match."
    )

    source_note = (
        "LGD identity/metadata only — no coordinates, elevation, or geometry. "
        "Not linked to research/pilot_points.py or any ERA5-Land grid cell. "
        f"'district' fields use the Zila Panchayat PRI-tier code (verified "
        f"parent of the selected block via Parent Localbody Code), which is "
        f"a DIFFERENT code namespace from LGD's separate Revenue-Department "
        f"district code. {revenue_note} 'block' fields use the Taluka "
        f"Panchayat PRI tier, a separate LGD entity from 'Development "
        f"Block' (blocks.csv), which was not fetched or joined."
    )

    rows = []
    for gp in sorted(gp_rows, key=lambda r: r["Localbody Name (In English)"]):
        rows.append({
            "state_name": TARGET_STATE,
            "state_lgd_code": state_code,
            "district_name": zp_row["Localbody Name (In English)"],
            "district_lgd_code": zp_row["Localbody Code"],
            "block_name": tp_row["Localbody Name (In English)"],
            "block_lgd_code": tp_row["Localbody Code"],
            "panchayat_name": gp["Localbody Name (In English)"],
            "panchayat_lgd_code": gp["Localbody Code"],
            "source": "Ministry of Panchayati Raj -- Local Government Directory (LGD), pri_local_bodies component",
            "source_url": (
                f"https://github.com/{REPO}/releases/tag/{RELEASE_TAG} "
                f"(asset pri_local_bodies.{ASSET_DATE}.csv.7z); "
                f"origin https://lgdirectory.gov.in"
            ),
            "retrieved_at": RETRIEVED_AT,
            "source_note": source_note,
        })
    return rows


FIELDNAMES = [
    "state_name", "state_lgd_code",
    "district_name", "district_lgd_code",
    "block_name", "block_lgd_code",
    "panchayat_name", "panchayat_lgd_code",
    "source", "source_url", "retrieved_at", "source_note",
]


def write_identity_csv(rows: list[dict], out_path: Path) -> None:
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    out_path = Path(__file__).resolve().parent / "karnataka_identity.csv"
    identity_rows = build_identity_rows()
    write_identity_csv(identity_rows, out_path)
    print(f"Wrote {len(identity_rows)} real Gram Panchayat identity rows -> {out_path}")
