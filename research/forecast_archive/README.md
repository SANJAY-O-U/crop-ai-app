# Prospective Open-Meteo forecast archive (Phase 2C, research only)

Nothing here is imported by `backend/` or `frontend/`, nothing is called from the live request path, and no model is
trained or saved. The archive records **what Open-Meteo actually returned** so that a correction can later be evaluated
on real forecast inputs instead of ERA5 reanalysis.

## Run

```bash
python research/forecast_archive/collector.py                 # one pass; safe to re-run (resumable, de-duplicated)
python research/forecast_archive/readiness.py                 # counts + frozen-rule readiness gate -> results/readiness.json
python research/forecast_archive/probe_history.py             # one-off availability probe of Open-Meteo's historical products
```

Schedule the collector at least twice a day, >= 12 h apart (one record per location per 12-h UTC slot):
e.g. Windows Task Scheduler / cron running the first command at 02:00 and 14:00 UTC.

## Storage (gitignored, like all raw data)

```
data/raw/open_meteo_forecast_archive/
  raw/<location_id>/<YYYYMMDD>/<retrieved_utc>_<sha12>.json    exact response bytes, written once (exclusive create), read-only
  index.jsonl      one line per successful retrieval
  errors.jsonl     one line per failed attempt (never replaced by mock/synthetic data)
data/processed/forecast_archive/                                derived tables (re-creatable); reference_<source>.csv go here
```

Back the raw directory up: it cannot be re-created for past dates.

### `index.jsonl` record (schema.INDEX_FIELDS)

| field | meaning |
|---|---|
| archive_version, record_id | schema version; `"<location_id>|<slot_start_utc>"` |
| location_id, location_set, role | block point requested; `live_demo_pilot` or `yelandur_research`; always `block_input` |
| provider, is_mock | always `open-meteo` / `false` (mock data is never archived) |
| retrieved_utc, slot_start_utc | UTC time the response was received; 12-h slot used for de-duplication |
| request_url, request_params | the exact request (same URL / daily variables / `timezone=auto` as production; `forecast_days=16`) |
| http_status, raw_path, raw_sha256, raw_bytes | provenance of the stored raw artifact |
| response_meta | latitude, longitude, elevation, timezone, timezone_abbreviation, utc_offset_seconds, generationtime_ms, daily_units, n_days |

Open-Meteo does **not** return which weather model produced a `best_match` value, so model identity cannot be archived;
the request and response headers/fields above are everything the provider exposes.

### Derived daily table (`flatten.py`, schema.DAILY_TABLE_FIELDS)

One row per (retrieval, target local day): `target_local_date`, `lead_days`, `retrieval_local_date`,
`retrieval_local_hour`, the five daily values under the **production names** (`temperature_min_c`, `temperature_max_c`,
`rainfall_mm`, `humidity_pct`, `wind_kmph`), `any_value_missing`, plus raw path/hash. Hash of every raw file is verified
when flattening.

## Day and lead definition

Open-Meteo `daily.time` values are **local calendar dates** (`timezone=auto` -> Asia/Kolkata, UTC+05:30, no DST) and the
response carries `utc_offset_seconds`. A forecast's target day is that local date; UTC calendar days are never used.
`lead_days = target_local_date - date(retrieved_utc + utc_offset)`; lead 0 is the (partly elapsed) day of retrieval.
Leads are never pooled in the evaluation (`pairing.evaluate_by_lead`).

## Locations (`location_registry.json`)

Block rows are forecast **inputs**; Panchayat rows are **targets** and are never forecast sources here.

Each registry row carries two independent fields:

- `location_role` - what the geography is used for: `live_demo_pilot` (the live CropCastAI demo geography) or
  `research_validation` (offline research/evaluation geography only; it is **not** the live CropCastAI demo geography).
- `is_demo_data` - whether the row's identity is placeholder data. It is unchanged and does not mean "live" or "research":
  the live demo rows are `true`, and the Yelandur research rows are `false` only because they carry real LGD identities.

- `live_demo_pilot`: `BLOCK-DEMO-001` + 3 demo Panchayats from `backend/app/geospatial/seed_data.py` (`is_demo_data=true`);
  they fall in **3** distinct ERA5-Land cells.
- `yelandur_research`: block point (mean of the 10 GP centroids) + 10 primary Gram Panchayats of the frozen Phase 2D
  dataset (real LGD identities, 1991 village-union proxy centroids); **4** cell groups, matching the frozen fold design.

## Reference (target) sources - never combined

`reference.py` fixes the contract of a daily reference table (one `reference_source` per table): `era5_land_cds`
(reanalysis proxy, ~5-day latency, a model) or `isd_station` (independent observations, not at the pilot Panchayats).
Pairing refuses a table that mixes sources. **No reference data exists yet for the archive dates**.

## Evaluation protocol (not run yet)

`pairing.build_pairs` -> per (issuance, Panchayat, target day, lead): block forecast (input), production baseline
(real `apply_baseline` from the backend, with the response elevation as in `_downscale`), reference value. The frozen
`daily_bridge` evidence rule is applied unchanged; `readiness.py` states what that rule needs (4 independent spatial
folds, all 4 calendar quarters, paired records) and refuses to proceed otherwise.
