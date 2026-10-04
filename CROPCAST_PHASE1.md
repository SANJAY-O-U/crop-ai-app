# CropCast — Phase 1 Development Notes

> **Update:** this is the historical Phase 1 note. Current production behaviour (provenance, fallback policy, health/readiness, error contract,
> deployment) is described in [`docs/PRODUCTION_READINESS.md`](docs/PRODUCTION_READINESS.md). The mock provider is now only used when
> `WEATHER_PROVIDER=mock` or as an explicitly labelled fallback (disable with `WEATHER_FALLBACK=error`).

Status: **foundation only**. This phase demonstrates the pipeline shape
(`Block Weather → Panchayat → Downscaled Weather → Visualization`) required by
SIH26074. It does **not** claim to solve SIH26074 — there is no trained ML
downscaling model, no risk engine, and no advisory engine yet. Those are
explicitly out of scope for this phase (see the approved architecture
proposal and the Phase 1 scope instructions).

## What was implemented

- A `WeatherProvider` abstraction (`backend/app/weather/base.py`) with two
  implementations: `OpenMeteoProvider` (real, live, no API key) and
  `MockWeatherProvider` (deterministic offline fallback). The active provider
  is chosen via the `WEATHER_PROVIDER` env var (`open-meteo` default, or
  `mock`), and the live provider automatically falls back to mock on any
  network failure so a demo never hard-crashes.
- A geospatial module with one pilot Block and three Panchayats, held as
  in-memory seed data (no database — see "What is mocked" below).
- A baseline downscaling method: real atmospheric-physics temperature
  lapse-rate correction, plus clearly-labeled *uncalibrated placeholder*
  heuristics for rainfall/humidity/wind, applied per-panchayat based on
  elevation difference from the block.
- Three new frontend screens (CropCast Dashboard, Panchayat Weather, Weather
  Map) added alongside the existing CropAI UI, reachable from a new
  "CropCast" nav tab. The existing Home/Detect/Result/Medicines screens were
  not modified.
- 27 automated tests covering provider normalization, geospatial lookups,
  downscaling math, and API response shapes (including that the existing
  CropAI endpoints still respond correctly).

## What is REAL

- **Weather data**: live from the Open-Meteo public API
  (https://api.open-meteo.com), by default. No API key needed, globally
  available by lat/lon. This is a legitimate, realistically-accessible
  provider — it is **not** IMD or any Indian government weather service.
- **Elevation values** in the seed data: fetched live from the Open-Meteo
  Elevation API for the exact pilot coordinates during development — genuine
  DEM-derived terrain data.
- **The temperature downscaling correction**: the International Standard
  Atmosphere environmental lapse rate (0.0065 °C/m) — an established physical
  constant, not a guess.
- **The pilot coordinates**: real, resolvable points on Earth, in the
  plateau/escarpment terrain near Nandi Hills, Karnataka — chosen
  specifically because the ~740m–1390m elevation range there makes the
  downscaling effect visible instead of a rounding-error-sized difference.

## What is MOCKED / SEEDED (and clearly labeled as such in the code and API)

- **Block and Panchayat identifiers** (`BLOCK-DEMO-001`, `PANCH-DEMO-001..3`)
  and **names** ("Demo Block", "Panchayat A/B/C") are fabricated placeholders,
  *not* LGD codes or any other official government identifier. Every record
  carries `"is_demo_data": true`.
- **Panchayat boundaries**: we use bare centroid points, not real boundary
  polygons/GeoJSON — no such data has been acquired yet.
- **The rainfall/humidity/wind downscaling coefficients**
  (`RAINFALL_OROGRAPHIC_FACTOR_PER_100M`, `HUMIDITY_ADJUSTMENT_PCT_PER_100M`,
  `WIND_FACTOR_PER_100M` in `backend/app/downscaling/baseline.py`) are
  illustrative placeholder magnitudes chosen to move panchayat values in a
  physically plausible *direction* — they are **not calibrated** against any
  real historical observations for this or any region. Every downscaling API
  response includes `"coefficients_calibrated": false` so this is never
  hidden from a caller.
- **`MockWeatherProvider`**: entirely synthetic, seeded-by-coordinate numbers,
  used only as an offline safety fallback and in tests — every response it
  produces is marked `"source": "mock"`, `"is_mocked": true`.

## How the baseline downscaling works

```
panchayat_value = block_value  ±  elevation-driven adjustment
```

1. Fetch **one** forecast for the block centroid (not per-panchayat — this is
   what makes it genuinely "coarse-to-fine downscaling" rather than just
   calling a fine-grained API three times and relabeling the result).
2. Compute `elevation_delta_m = panchayat_elevation - block_elevation`.
3. Temperature: `shift = -0.0065 * elevation_delta_m` (real physics).
4. Rainfall/humidity/wind: apply the placeholder heuristic factors above,
   clamped to sane bounds so extreme deltas can't produce absurd multipliers.
5. If elevation is unavailable for either point, no adjustment is applied and
   the block's value is returned unmodified for that panchayat — the system
   never fabricates a number it can't justify.

Every response's `adjustment` object shows the exact elevation values and
coefficients used, so the computation is auditable, not a black box.

## What remains for the ML downscaling phase (not started)

- Acquire historical block-forecast vs. ground-truth pairs (proxy ground
  truth via IMD gridded data or ERA5-Land reanalysis, sampled at panchayat
  centroids — see the approved architecture doc, Section D) for the pilot
  block.
- Train a regression model (start with linear regression, escalate to
  gradient-boosted trees only if justified) to replace the placeholder
  rainfall/humidity/wind coefficients with values learned from that data.
- Add a `method: "ml_corrected"` path in `downscaling/service.py` alongside
  the existing baseline, with the baseline kept as the fallback for any
  panchayat/variable without enough training data.
- Validate against held-out historical points (RMSE/MAE) before trusting the
  corrected numbers over the baseline.

## Known limitations of this phase

- Only one block and three panchayats exist; nothing else is wired up for
  additional blocks.
- No persistence — restarting the backend resets nothing (there's nothing
  stateful to reset yet), but there is also no History.
- No Risk Engine, no CropAI integration, no Advisory Engine — those are
  later, separately-approved phases.
- Wheat's known broken UI entry in the existing CropAI Detect page is
  untouched, per explicit instruction.
