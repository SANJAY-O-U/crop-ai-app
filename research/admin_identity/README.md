# Karnataka Administrative Identity — Stage 1

Real Panchayat identity/metadata for one Karnataka block, sourced from the
Ministry of Panchayati Raj's Local Government Directory (LGD). This is
**identity data only** — no coordinates, elevation, or geometry. It is
deliberately unlinked from `research/pilot_points.py`, ERA5-Land, and every
other spatial/weather artifact in this repo.

## What's here

- `fetch_lgd_identity.py` — the reproducible fetch script (real HTTP
  requests to a public GitHub release, no CAPTCHA/GUI/auth needed; verified
  with a plain `curl -I` this session).
- `karnataka_identity.csv` — the committed output of that script: 12 real
  Gram Panchayats, one block, one district, one state.
- `identity_data.py` — a thin loader/validator over the CSV.

## Exact source

| | |
|---|---|
| Ultimate origin | Ministry of Panchayati Raj, Government of India — Local Government Directory, https://lgdirectory.gov.in |
| Mirror used | https://github.com/ramSeraph/opendata (community scrape of the same official site, chosen because the official portal's own download is CAPTCHA-gated with no documented API — see the Phase 2C investigation report) |
| Release | `lgd-latest-extra1` |
| Exact assets | `states.22Sep2026.csv.7z`, `districts.22Sep2026.csv.7z`, `pri_local_bodies.22Sep2026.csv.7z` |
| Retrieved | 2026-09-22 |
| Asset URL pattern | `https://github.com/ramSeraph/opendata/releases/download/lgd-latest-extra1/<component>.22Sep2026.csv.7z` (anonymously downloadable, verified via `curl -I` → 200 OK, no auth) |

## Which file has what, and how the hierarchy is actually joined

LGD is not one flat table — it's several separate component tables, and
**not all of them join to each other by code**. This matters:

- **`states.csv`**: State Code / State Name. Karnataka = code `29`. This
  code is consistent across every other LGD table checked.
- **`districts.csv`**: Revenue Department districts — District Code /
  District Name. This is a *different* administrative concept from the
  Panchayati Raj hierarchy below, with its **own separate code namespace**.
- **`pri_local_bodies.csv`**: the actual Panchayati Raj Institution
  hierarchy — Zilla Parishad (`Localbody Type Code` 1) → Panchayat Samiti
  (type 2) → Gram Panchayat (type 3), all in ONE table, joined via
  `Parent Localbody Code` pointing at another row's `Localbody Code`. In
  Karnataka these are locally named **Zila Panchayat**, **Taluka
  Panchayat**, and **Gram Panchayat** respectively (verified: Karnataka has
  31 Zila Panchayats, 238 Taluka Panchayats, 5,946 Gram Panchayats in this
  file — the 5,946 figure matches Karnataka's well-known real-world Gram
  Panchayat count, a good sanity check).

This dataset uses **`pri_local_bodies.csv` alone** for the
State→District→Block→Panchayat chain, because it is the only table with
**code-verified** parent/child links all the way from Zila Panchayat down
to Gram Panchayat. `district_lgd_code` and `block_lgd_code` in
`karnataka_identity.csv` are therefore `pri_local_bodies.csv`'s own
`Localbody Code` values for the Zila Panchayat and Taluka Panchayat tiers —
**not** `districts.csv`'s Revenue District Code, and **not** LGD's separate
`blocks.csv` ("Development Block") entity type.

## Verified ambiguity — do not silently join these

Checked directly against both files this session, for the exact district
used here:

| Table | Name | Code |
|---|---|---|
| `pri_local_bodies.csv` (Zila Panchayat, used here) | **Bagalkot** | `479` |
| `districts.csv` (Revenue District) | **Bagalkote** | `524` |

Different spelling, different code, **no shared key**. A naive string-match
join (`Bagalkot` ≈ `Bagalkote`) is the only way to relate them, and this
codebase does not treat that as a verified equivalence — `fetch_lgd_identity.py`
records the districts.csv candidate in each row's `source_note` for
disclosure only, never as an asserted code link.

Separately, LGD's `blocks.csv` ("Development Block") is yet a **third**,
independent entity type. It was checked for Karnataka's Bagalkote district
and found to contain zero rows under that exact district-name spelling
(same mismatch as above) — it was not fetched by `fetch_lgd_identity.py`
and no attempt was made to reconcile it with the Taluka Panchayat tier used
here.

## Selected entities

- **State**: Karnataka (`29`)
- **District (Zila Panchayat)**: Bagalkot (`479`)
- **Block (Taluka Panchayat)**: Guledagudda (`296788`) — chosen for a
  moderate, manageable Gram Panchayat count (12) among Bagalkot's 8 taluks
  (range: 12–30 GPs each)
- **Panchayats (Gram Panchayat)**: all 12 real Gram Panchayats under
  Guledagudda — a complete taluk, not a cherry-picked subset

## Reproducing

```bash
python research/admin_identity/fetch_lgd_identity.py
```

Downloads the three named release assets into `data/raw/lgd/` (gitignored)
and regenerates `karnataka_identity.csv`. Re-running with a later
`ASSET_DATE` will pull a more recent LGD snapshot — the underlying source
is updated roughly daily.

## What this Stage 1 dataset does NOT contain

- No coordinates, centroids, or boundaries of any kind
- No elevation
- No relationship to `research/pilot_points.py`'s points or to any
  ERA5-Land grid cell — nothing here has been spatially resolved yet
