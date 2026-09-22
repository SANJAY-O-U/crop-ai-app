# CropCast Research Pipeline — Phase 2A

Data acquisition + preprocessing for the Block → Panchayat downscaling
model. This code is **research-only**: nothing under `backend/app/` imports
anything from here, and nothing here modifies the live CropCast API.
`backend/app/downscaling/baseline.py`'s temperature constant is *read* by
`pipeline/baseline_eval.py` (to evaluate the real production formula, not a
re-typed copy), but nothing here writes to or changes it.

## Status as of Phase 2A

**No real ERA5-Land data has been acquired yet.** Copernicus CDS
credentials are not configured in this environment, and this document does
not claim otherwise anywhere below. Every pipeline stage is implemented and
unit-tested against synthetic fixtures, but the actual acquisition step
requires a human to complete a browser-based signup (see below) — that
cannot be done by an automated agent.

## Why "reanalysis proxy", never "observation"

Per the Phase 1.5 investigation: India has no panchayat-density real weather
station network. ERA5-Land is a *reanalysis* — a model-reconstructed, quality
global dataset, not a direct sensor reading. Every value this pipeline
produces is labeled `"reanalysis proxy"` and `source: "era5_land_reanalysis_proxy"`
for exactly this reason. Treat any resulting "accuracy" number as bounded by
how well ERA5-Land represents this specific terrain — not as ground truth.

## Getting CDS credentials (manual, one-time, cannot be automated)

1. Create a free account at <https://cds.climate.copernicus.eu>.
2. Log in and open the ERA5-Land dataset page:
   <https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land>.
   Accept that dataset's **Terms of Use** — this is a one-time, in-browser
   click that has no API equivalent. Requests fail until this is done.
3. Go to <https://cds.climate.copernicus.eu/profile> and copy your
   **Personal Access Token**.
4. Configure credentials one of two ways:
   - **Environment variables** (preferred):
     ```bash
     export CDSAPI_URL=https://cds.climate.copernicus.eu/api
     export CDSAPI_KEY=<your-personal-access-token>
     ```
   - **Or** create `$HOME/.cdsapirc`:
     ```
     url: https://cds.climate.copernicus.eu/api
     key: <your-personal-access-token>
     ```

Credentials are never hardcoded anywhere in this codebase — see `config.py`.

## Install

```bash
pip install -r research/requirements.txt
```
(Deliberately separate from `backend/requirements.txt` — the live app never
needs `xarray`/`netCDF4`/`cdsapi`.)

## Pipeline steps, in order

```bash
# 1. Acquire a SMALL pilot ERA5-Land file (3 days, June 2023, 5 variables,
#    a small bounding box around the pilot block + 3 demo panchayats).
#    Requires credentials from the section above. Real network call.
python research/scripts/run_pilot_acquisition.py

# 2. Convert the raw .nc file into one normalized CSV per point
#    (data/processed/weather/<id>.csv), with documented unit conversions.
python research/scripts/run_normalize.py

# 3. Join the block (coarse) and panchayat (fine) series into training
#    pairs (data/training/training_pairs.csv).
python research/scripts/run_build_training_pairs.py

# 4. Compute real MAE/RMSE for (a) the naive block-value-as-is baseline and
#    (b) Phase 1's elevation-based temperature correction, against the
#    ERA5-Land proxy target. Writes data/evaluation/baseline_metrics.json.
#    Refuses to report a number if there isn't enough data — see the
#    script's own output.
python research/scripts/run_baseline_eval.py
```

Each script prints an explicit `BLOCKED` / `INSUFFICIENT DATA` message and
exits non-zero if an earlier step hasn't produced real output yet — none of
them silently proceed with fabricated data.

## Data directory layout

```
data/
  raw/era5_land/       # exactly what CDS returns — untouched .nc files
  processed/weather/   # one normalized CSV per point (block + panchayats)
  processed/geospatial/  # reserved for elevation/land-cover extracts (not populated yet)
  processed/features/    # reserved for joined covariate tables (not populated yet)
  training/             # training_pairs.csv — the coarse->fine dataset
  evaluation/            # baseline_metrics.json and future model eval outputs
```

**Nothing under `data/` is committed to git except `.gitkeep` placeholders**
(see the repo's root `.gitignore`) — every file in `data/` is either a
multi-MB download or something regenerable by re-running the scripts above.
Only the pipeline *code* under `research/` is version-controlled.

## What's safe to commit vs. what must stay ignored

| Path | Commit? |
|---|---|
| `research/**/*.py`, `research/requirements.txt`, `research/README.md` | Yes |
| `data/**/.gitkeep` | Yes |
| `data/raw/**`, `data/processed/**`, `data/training/**`, `data/evaluation/**` (actual files) | **No** — gitignored |
| `~/.cdsapirc`, any `*.cdsapirc` | **No** — gitignored, contains your personal token |

## Units reference (see `pipeline/units.py` for the code)

| Variable | Raw ERA5-Land unit | Converted to | Formula |
|---|---|---|---|
| `temperature_c` | Kelvin | Celsius | `C = K - 273.15` |
| `dewpoint_c` | Kelvin | Celsius | `C = K - 273.15` |
| `relative_humidity_pct` | *(not a raw ERA5-Land variable)* | % | Magnus-Tetens formula from temperature + dewpoint |
| `rainfall_mm` | metres, **accumulated per forecast cycle** | mm, per-hour | de-accumulate (diff consecutive hours within a 00/12 UTC cycle), then `mm = m * 1000` |
| `wind_speed_kmph` | m/s (u, v components) | km/h | `speed = sqrt(u^2+v^2) * 3.6` |

## Tests

```bash
cd research && python -m pytest -q
```
36 tests, all against synthetic fixtures (`research/synthetic_fixtures.py`,
explicitly documented as NOT real ERA5-Land data) — they verify the pipeline
*code* is correct; they say nothing about real-world accuracy, which
requires the actual acquisition in the section above.
