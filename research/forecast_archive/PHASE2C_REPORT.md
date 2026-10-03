# Phase 2C - real forecast input validation: infrastructure report

**Phase 2C evaluation is not yet statistically ready; prospective forecast archiving must run first.**

Question this phase serves: *does a correction trained/evaluated against real archived Open-Meteo forecast inputs improve
Panchayat-level temperature-minimum forecasts over the uncorrected block forecast?* This report establishes the data
pipeline and protocol. No result is reported because none can yet be computed honestly. Nothing here changes the live
API, the frontend, or any model; no model was trained or saved.

## 1. What historical forecast data exists locally
None. A search of the repository and `data/` found Open-Meteo only in code and comments; no archived forecast, raw
response or derived forecast table existed before this phase. ERA5/ERA5-Land and ISD data exist, but those are
reanalysis and observations, not forecasts, and were not substituted.

## 2. What cannot be recovered
The exact forecasts the live product produced on past days (`best_match`, issued at a particular time, with a particular
lead) were never stored and cannot be reconstructed. Open-Meteo does not return the underlying model for `best_match`.

A one-off probe (`probe_history.py`, raw files in `data/raw/open_meteo_history_probe/`, summary in
`results/history_probe.json`) shows that Open-Meteo exposes two *different* historical products for the demo block
point (all returned HTTP 200 with non-null values):

| Product | Probe result | Caveat |
|---|---|---|
| Historical Forecast API | daily `temperature_2m_min` for 2022-06 and 2023-06 | a continuous series stitched from successive model runs (roughly lead 0), not issuance-by-issuance forecasts |
| Previous Runs API | hourly values and `_previous_day1/3` for 2023-06 and 2025-06 | per-lead values exist, but the model mix and availability differ by period and are not the production `best_match` request |

These could support a **retrospective** study, but they are not the production input, so they were **not** used or
mixed into this archive. Whether to build such a dataset is a separate decision (see section 13).

## 3. Archive schema
Documented in `README.md` and enforced in `schema.py`. Immutable raw response files (exclusive create, read-only,
SHA-256 in the index) + `index.jsonl` (retrieval time, slot, request URL/params, HTTP status, raw path/hash, response
metadata: lat/lon, elevation, timezone, UTC offset, generation time, units) + `errors.jsonl` (HTTP/timeout/network/shape
failures). Processed values are *derived* from the raw files by `flatten.py` and verified against the hashes.

## 4. Pilot locations
`location_registry.json` (generated from the live seed data and the frozen Phase 2D dataset; nothing new invented):

| Set | Block input point | Target Panchayats | Distinct ERA5-Land cells | Demo data |
|---|---|---|---|---|
| `live_demo_pilot` | `BLOCK-DEMO-001` (13.40, 77.73) | 3 (`PANCH-DEMO-001..003`) | **3** | yes |
| `yelandur_research` | `YELANDUR-BLOCK-PROXY` (mean of 10 GP centroids) | 10 LGD Gram Panchayats | **4** | no (geometry = 1991 proxy) |

Block rows are forecast inputs; Panchayat rows are targets. Every row has `location_role`: `live_demo_pilot` for the first set and `research_validation` for Yelandur (offline research/evaluation geography, **not** the live CropCastAI demo geography); it is independent of `is_demo_data`, which only says whether the identity is placeholder data. Panchayat-level Open-Meteo output is **not** archived as a
reference and is never treated as ground truth. The Yelandur set was included because the frozen "3 of 4 folds" rule needs 4
independent spatial groups and the live demo pilot has only 3; this is existing project geography, not new geography,
but it is a choice you may want to confirm.

## 5. Target / reference sources
- INPUT: real Open-Meteo forecast at the block point.
- TARGET (one source at a time, `reference.py` refuses mixtures):
  - `era5_land_cds` - reanalysis proxy (not observation). Covers the Yelandur GPs through 2023-12-31 and the demo pilot for a
    72-hour June 2023 window. **No reference data exists for the archive dates**; it would need a new CDS acquisition after
    the usual ~5-day latency.
  - `isd_station` - independent observations, 2023 only, 4 stations that are 6-17 km from Panchayat centroids and **none at the
    live demo pilot**. Not usable for the archive dates without new acquisition and a separate, station-based protocol.

## 6. Forecast lead-time definition
`lead_days = target_local_date - date(retrieved_utc + utc_offset_seconds)`. Lead 0 is the partly elapsed day of retrieval;
`retrieval_local_hour` is stored so it can be excluded or stratified. Leads 0-15 are preserved (`forecast_days=16`).

## 7. Timezone / day definition
Open-Meteo `daily.time` are local calendar dates (`timezone=auto` -> Asia/Kolkata, UTC+05:30, no DST). Target days are those
local dates; reference hourly data are converted to the same IST day (`local_date_ist`, as in `daily_bridge`). UTC calendar
days are never used for pairing (test: 2026-10-04 20:00 UTC is already 2026-10-05 in IST).

## 8. Pairing methodology
`pairing.build_pairs`: issuance -> target local day -> block daily forecast -> (for each Panchayat of that block) matching
reference day -> evaluation record with `lead_days`. The production baseline is the real backend `apply_baseline`
(through `daily_bridge.baselines`), using the response's elevation as the live service does. Forecast days with any
missing value and days with no reference are dropped and **counted**, never filled. `evaluate_by_lead` reports MAE/RMSE/
bias and skill vs block-as-is per lead; leads are not pooled.

## 9. Leakage protections
Candidate training (future) must use the frozen `daily_bridge` design: leave-one-cell-group-out spatial folds, temporal
holdout with a 7-day embargo, no random row splits. Panchayats in one ERA5-Land cell are one spatial unit. The reference is
never an input. Raw forecasts are immutable and hash-verified, so inputs cannot be edited after seeing results.

## 10. Planned evaluation
Primary variable: temperature minimum; other variables keep the infrastructure only. Compare block-as-is, production
baseline and the candidate (the `C_daily_hgb` temperature-min definition from `daily_bridge`) per lead, with the **frozen**
evidence rule unchanged: beat block-as-is on MAE and RMSE, in >= 3/4 folds and >= 3/4 quarters, bootstrap interval above
zero, and beat the production baseline. Rainfall and wind remain pass-through.

## 11. Current dataset size (first real collection, 2026-10-03T19:25Z)
| Item | Value |
|---|---|
| Forecast issuances | 1 (2 block points: demo block, Yelandur block proxy) |
| Forecast rows (location x target day) | 32 (16 target days each, leads 0-15) |
| Failed attempts | 0 |
| Panchayats / unique ERA5-Land cells / independent spatial groups | demo pilot 3 / 3 / 3; Yelandur 10 / 4 / 4 |
| Paired target observations | **0** (no reference for these dates) |
| Real-data observation | the lead-15 day arrived with all five values null for both points; it is recorded as missing, not filled |

## 12. Limitations
- A single issuance exists; at most two per day will accumulate per location.
- The live demo pilot cannot satisfy the "3 of 4 folds" rule (3 spatial groups); Yelandur can (4) but is not the live pilot.
- Target data for the archive dates must still be acquired; ERA5-Land is a model, not observation, and no station is at the pilot.
- The model behind `best_match` is not observable and may change over time; model changes will appear as non-stationarity.
- All four calendar quarters must be covered; one season of data cannot support the frozen quarter criterion.
- Seed-data placeholders (demo Panchayats) remain placeholders; Yelandur centroids are a 1991 spatial proxy.

## 13. Is there enough data to run the real-forecast experiment?
**No.** `readiness.py` (frozen rule applied as-is) fails because: there are no paired forecast/reference records; the live demo
pilot has only 3 independent spatial groups (Yelandur has 4); and only one calendar quarter can ever be covered by data
starting in October 2026 until archiving continues through July 2027 (and a meaningful sample needs full quarters).

Phase 2C evaluation is not yet statistically ready; prospective forecast archiving must run first.

Decisions left to you: (a) confirm the Yelandur research set as the evaluation geography for the frozen 4-fold rule;
(b) whether to *additionally* build a clearly labelled retrospective dataset from the Previous Runs / Historical Forecast
APIs (faster, but not the production input and not issuance-exact); (c) which reference source to acquire for the archive
dates (ERA5-Land via CDS is the only one covering the Yelandur Panchayats).
