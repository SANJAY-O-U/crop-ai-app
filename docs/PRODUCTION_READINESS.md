# CropCastAI — Production Candidate V1

**Status: production candidate, not a validated forecasting product.** Production forecasts use a *deterministic,
uncalibrated elevation baseline*. No machine-learning correction is deployed, and none is enabled by any setting.
Nothing in this document is an accuracy claim: no accuracy of the Panchayat estimates has been measured against real
observations.

## 1. What is production and what is research

| | Production (`backend/`, `frontend/`) | Research (`research/`, `data/`) |
|---|---|---|
| Weather input | Open-Meteo daily forecast at the **block** point (live, or explicitly labelled mock) | ERA5 / ERA5-Land reanalysis, ISD stations, archived forecasts |
| Panchayat method | `baseline`: lapse-rate temperature shift + three uncalibrated heuristics (`backend/app/downscaling/baseline.py`) | HGB / ridge correction experiments (offline only) |
| Status of results | serves users | experiments; **not imported by, and never feeding, any production response** |
| Evidence | none claimed | frozen evidence rule (`research/daily_bridge/config.py`); the Phase 2C real-forecast evaluation is **not yet statistically ready** |

Rules enforced by tests: production code does not import `research`/`joblib`/`pickle`; every downscaling response
carries `provenance.research_data_used = false`, `provenance.ml_correction_enabled = false`, `method = "baseline"` and
`model_version = null`; `DOWNSCALING_METHOD=ml_corrected` is ignored (with a log warning) and the baseline is used.

## 2. Current production capabilities

- **Live weather**: `GET /api/v1/weather/block/{id}/forecast` — Open-Meteo `/v1/forecast`, 1–16 days, `timezone=auto`.
- **Panchayat estimates**: `GET /api/v1/downscaling/{panchayat_id}/forecast` and `/block/{block_id}/forecast` — the block
  forecast is fetched once and adjusted per Panchayat by elevation (baseline only).
- **Geography**: `GET /api/v1/geospatial/...` — one **demo** block and three **demo** Panchayats (`is_demo_data=true`,
  placeholder identities and approximate coordinates near Nandi Hills, Karnataka).
- **Disease detection**: `POST /api/detect`, `GET /api/crops` — 9 crop classifiers (tomato, potato, pepper, banana, cotton,
  mango, onion, rice, sugarcane) and 21 disease classes. *Accuracy of these classifiers has not been verified in this
  repository.* The model weights (`*.pth`) are git-ignored; `GET /ready` reports how many are present
  (`disease_detection_models`). Verify they exist on the deployed instance.
- **Frontend**: unchanged UI. The only frontend change in this milestone is that "Today" is evaluated in the forecast's own
  timezone (see section 5).

## 3. Request flow and failure behaviour

```
Open-Meteo ──► OpenMeteoProvider (timeouts, 1 conservative retry, strict validation)
                    │ ok                         │ ProviderError(kind)
                    ▼                            ▼
             bounded TTL cache           WEATHER_FALLBACK=mock (default): labelled mock  ── or ──
                    │                    WEATHER_FALLBACK=error: HTTP 503 / 502
                    ▼
        ForecastCorrectionStrategy (baseline) ──► Panchayat forecast + provenance
```

A provider failure is never returned as weather. Three states are distinguishable in every response:

| `block_source.data_origin` | Meaning |
|---|---|
| `live_provider` | A real Open-Meteo response (possibly served from the cache: `from_cache=true`, original `retrieved_at` kept) |
| `mock_configured` | `WEATHER_PROVIDER=mock` (tests/offline development) |
| `mock_fallback` | The live provider failed and `WEATHER_FALLBACK=mock`; `fallback_reason` says why (`timeout: …`, `connection: …`, `http_error: HTTP 503`, `malformed_response: …`, …) |

`is_mocked` (existing field, used by the frozen UI's "Sample data (offline)" chip) is `true` for both mock origins.
**Recommended for production: `WEATHER_FALLBACK=error`** so users never see synthetic numbers.

### Reliability details
- Timeouts: connect 3 s, read 8 s. At most one retry, only for connect-level failures and 5xx responses (fixed 0.3 s pause).
  Read timeouts, 4xx and bad payloads are not retried. Worst case ≈ 8 s (read timeout) or ≈ 6.3 s (two connect timeouts).
- Failure cooldown: after a failure the provider is not called again for 30 s (`WEATHER_FAILURE_COOLDOWN_S`) — no hammering.
- Cache: successful live responses only, ≤ 64 entries, 600 s TTL (`WEATHER_CACHE_TTL_S`; 0 disables). A cached response is
  labelled (`from_cache`, `cache_age_s`) and keeps its original `retrieved_at`. Mock/fallback data is never cached.
- Null values: Open-Meteo returns `null` at the end of the 16-day horizon. Such days are **omitted** (never filled); they
  are listed in `omitted_dates` and `partial=true`. A response with no usable day is an error (`empty_forecast`).
- Rejected as a whole (`invalid_payload` / `malformed_response` / `unexpected_units`): out-of-range values, `tmin > tmax`,
  non-numeric values, array-length mismatch, duplicate or unsorted dates, unexpected units, missing blocks.

### Validation bounds (generous enough to admit real extremes)
temperature −90…60 °C and `tmin ≤ tmax`; rainfall 0…2000 mm/day; humidity 0…100 %; wind 0…500 km/h; latitude ±90, longitude
±180; elevation −500…9000 m (an out-of-range provider elevation becomes *unknown*, not an error).

## 4. API contract

Existing fields are unchanged. Additive fields (the frontend does not need to display any of them):

`block_source` (`PointForecast`): `data_origin`, `fallback_reason`, `retrieved_at` (UTC), `forecast_generated_at` (always `null`
for Open-Meteo, which does not expose the model-run time), `timezone`, `utc_offset_seconds`, `requested_days`,
`forecast_horizon_days`, `partial`, `omitted_dates`, `from_cache`, `cache_age_s`.

Downscaled forecast: `model_version` (`null` — the baseline has no trained model) and `provenance`:
`weather_source`, `data_origin`, `is_mocked`, `fallback_used`, `fallback_reason`, `retrieved_at`, `from_cache`, `timezone`,
`day_definition`, `forecast_horizon_days`, `partial`, `omitted_dates`, `correction_method`, `correction_status`,
`model_version`, `block_elevation_m`, `panchayat_elevation_m`, `elevation_available`, `ml_correction_enabled` (always false),
`research_data_used` (always false). `method` is `"baseline"`; `"ml_corrected"` is never returned.

### Errors (frontend-compatible: `detail` stays a string)
```json
{"detail": "Panchayat 'X' not found.", "error": {"code": "not_found", "message": "...", "request_id": "..."}}
```
| Status | `error.code` | When |
|---|---|---|
| 404 | `not_found` | unknown block / Panchayat / route |
| 405 | `method_not_allowed` | wrong HTTP method |
| 422 | `invalid_request` | invalid parameters (`error.fields` lists them, e.g. `days` outside 1–16) |
| 503 | `weather_unavailable` | provider unreachable / timed out and `WEATHER_FALLBACK=error` (`Retry-After: 30`) |
| 502 | `weather_upstream_invalid` | provider answered with an unusable response and `WEATHER_FALLBACK=error` |
| 500 | `internal_error` | anything unexpected: generic message, no stack trace; details only in server logs |

Every response carries `X-Request-ID` (an incoming valid id is reused).

## 5. Day and timezone definition

`daily[].date` is the **local calendar date at the forecast point in the provider's timezone** (Open-Meteo `timezone=auto`;
Asia/Kolkata, UTC+05:30, for the pilot). Dates pass unchanged provider → block forecast → Panchayat forecast → frontend; nothing
shifts UTC timestamps into days. The mock provider uses the same IST day (not the server's UTC day). The frontend decides
"Today" with `nowInTimezone(block_source.timezone)`, so a viewer in another timezone sees the same day labels as the forecast.
Regression tests cover the UTC/IST boundary (2026-10-04 20:00 UTC is already 2026-10-05 in IST) on the backend and frontend.
Lead 0 (today) is a partly elapsed day.

## 6. Downscaling cases (equations unchanged)

| Situation | Result | `provenance.correction_status` |
|---|---|---|
| Weather unavailable, fallback `error` | HTTP 503/502, no forecast | — |
| Weather unavailable, fallback `mock` | labelled mock block forecast, baseline applied to it | `applied` (+ `fallback_used=true`) |
| Weather ok, elevation missing | block values returned unchanged | `elevation_unavailable` |
| Weather ok, elevation not finite / outside −500…9000 m | block values unchanged | `elevation_invalid` |
| Weather ok, \|Δelevation\| > 3000 m | block values unchanged (almost certainly a bad elevation) | `elevation_delta_implausible` |
| Weather ok, elevation ok | baseline applied | `applied` |

Baseline outputs are bounded: rainfall ≥ 0 (and its factor clamped to 0.5–1.6), humidity 0–100, wind ≥ 0. Block elevation
0 m is respected (`is None` check). The coefficients for rainfall, humidity and wind are **placeholders, not calibrated**
(`coefficients_calibrated=false` in every response).

## 7. Health and readiness

- `GET /health` — **liveness**: `{"ok": true}` if the process answers. Use for Render's health check and uptime pings.
- `GET /ready` — **ready to serve weather**: checks the configured provider name is known, the geography is loaded, and the
  correction strategy resolves to the baseline. It does **not** call Open-Meteo, so an upstream outage never removes the
  service from rotation; it degrades per request instead. Returns 503 only for a broken local configuration. It also reports
  informational provider status (`last_success_at`, `last_failure_at`, fallback policy), event counters, the active/requested
  correction method, and how many disease-model files are present (this does not affect readiness).

## 8. Observability

One JSON line per event on stdout (collected by Render). Never logged: bodies, uploaded images, headers, query strings, secrets.

| Event | Meaning |
|---|---|
| `http_request` | method, path, status, latency_ms, request_id (not logged for `/health`) |
| `weather_provider_success` / `weather_provider_failure` | provider, latency, days, date range / failure `kind`, upstream status |
| `weather_fallback_used` | a labelled mock was returned (reason kind) |
| `weather_cache_hit` | cached live forecast reused |
| `invalid_weather_payload` | provider payload rejected (malformed / out of bounds / units / empty) |
| `downscaling_baseline_used` | block id, Panchayat count, correction statuses, data origin, date range |
| `request_validation_failed`, `unhandled_exception`, `downscaling_method_ignored`, `cors_wildcard_in_production` | operational warnings |

## 9. Configuration and Render deployment checklist

> The authoritative, up-to-date deployment checklist (disease-model artifacts, `/ready` fields, smoke tests, rollback) is [`PRODUCTION_DEPLOYMENT.md`](PRODUCTION_DEPLOYMENT.md); the table below predates it.

Variables are documented in `backend/.env.example`. No secrets are required.

| Variable | Recommended production value |
|---|---|
| `APP_ENV` | `production` (hides the `origins` field on `/`, warns on wildcard CORS) |
| `ALLOWED_ORIGINS` | the Vercel frontend origin(s), comma-separated — **required** (unset = `*`) |
| `WEATHER_FALLBACK` | `error` |
| `WEATHER_PROVIDER` | `open-meteo` |
| `DOWNSCALING_METHOD` | `baseline` (default) |
| `MAX_UPLOAD_MB`, `LOG_LEVEL`, `WEATHER_CACHE_TTL_S`, `WEATHER_FAILURE_COOLDOWN_S` | defaults are fine |

Render settings (the repository has no `render.yaml`; the service is configured in the Render dashboard, so verify there):
root directory `backend`; build `pip install -r requirements.txt`; start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
(no `--reload`); health check path `/health`; set a Python version explicitly (dependencies are unpinned). Development-only
dependencies live in `backend/requirements-dev.txt` (pytest). Frontend: Vercel with `VITE_API_URL` set to the Render URL.

## 10. Security review (lightweight, non-destructive)

No secrets in the repository (`.env` is git-ignored; none required). No debug mode or reload in production. No path-based file
access (uploads are read from the request only); upload size is now capped (`MAX_UPLOAD_MB`, default 15 MB → 413) and content
types are checked. Error responses carry no stack traces. CORS defaults to `*` when `ALLOWED_ORIGINS` is unset → set it.
Model loading now uses `torch.load(..., weights_only=True)` (verified on all nine classifiers) and no longer downloads ImageNet weights at runtime. Findings left open: unpinned dependencies; `/docs` and `/openapi.json` are public; no rate limiting or authentication (the API is
public and the detect endpoint is CPU-heavy); uploaded images are decoded with Pillow's default decompression-bomb limit only.

## 11. Performance observations (local, one run)

Cold block request (live Open-Meteo): ≈ 2–3 s. Same request from the cache: ≈ 7 ms server time (≈ 16 ms through the test client).
Geospatial and health endpoints: ≈ 10–15 ms. Response size for a 7-day, 3-Panchayat block: ≈ 10 KB. The frontend makes one
weather-bearing request per page load (`/downscaling/block/{id}/forecast`); the provider is called once per cache window, not per
Panchayat. A single-process, in-memory cache means each Render instance has its own cache.

## 12. Known limitations

- Demo geography only: one block, three placeholder Panchayats; approximate coordinates; not official boundaries.
- The baseline is a heuristic: only the temperature lapse rate is physical; rainfall/humidity/wind factors are uncalibrated.
- No measured accuracy for Panchayat estimates; no uncertainty or confidence values are provided (none are invented).
- No crop-risk, disease-risk or advisory data. The UI says so explicitly.
- Open-Meteo is not an official Indian meteorological source; its model for `best_match` is not exposed.
- Research datasets and experiments are not production inputs; the real-forecast validation needs months of prospective archiving.

## 13. Tests

```bash
cd backend && python -m pytest tests          # backend (pip install -r requirements-dev.txt)
cd frontend && npm test && npm run build      # forecast-model tests + production build
```
Research suites are separate (`research/`) and are not required for production changes.
