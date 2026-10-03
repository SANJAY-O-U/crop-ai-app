# Stage 5 — Observational validation of the frozen Stage 4D model

**Stage 4D was evaluated against the ERA5-Land reanalysis proxy. Stage 5
evaluates the frozen Stage 4D model against independent observations.**

Observations are an independent validation source with their own errors;
ERA5-Land is a reanalysis proxy. Nothing here retrains, tunes or modifies
Stage 4D, and nothing is imported by the live application.

## Pipeline and gates

| Gate | Module | What it establishes |
|---|---|---|
| 1 Source discovery | `discover_sources.py` | IMD DSP and KSNDMC need a user-initiated request/account; NOAA NCEI ISD is the authoritative source obtainable now |
| 2 Metadata/coverage | `acquire_observations.py` | ISD 2023 files for matched stations; URL, size, SHA-256, retrieval time |
| 3 Matching | `station_matching.py` | pre-declared PRIMARY / NEARBY_DIAGNOSTIC / EXCLUDED rules (`criteria5.py`) |
| 4 Alignment | `temporal_alignment.py` | exact UTC top-of-hour pairing; rainfall only over each report's own accumulation period |
| 5 QC | `observation_qc.py` | source QC codes preserved; every exclusion counted by reason; nothing silently deleted |
| 6 Frozen model | `gate6.py` (own step) | each needed Stage 4D area fold is re-fitted with unchanged code; A1/A2/C4 prediction hashes must equal Stage 4D's; verified predictions are checkpointed per fold |
| — Evaluation | `evaluate_frozen_model.py --step evaluate` | reads only the verified checkpoints (no refit); refuses to start unless Gate 6 is recorded |

`provenance.py` records the independence audit: Stage 4C/4D artifacts are
unchanged, the observation files were written after Stage 4D finished, no
development code references observations, and Gate 6 reproduced the model.

## Pre-declared rules (`criteria5.py`, fixed before any observation value was read)

- **Evaluation period:** 2023 only (the Stage 4D test year).
- **PRIMARY:** the station lies inside an included Panchayat polygon, and its
  nearest ERA5-Land cell is that area's target cell.
- **NEARBY_DIAGNOSTIC:** the station's nearest cell is a target cell, or
  within 1 cell of one. Reported separately and never pooled with PRIMARY.
- **Accepted ISD quality codes:** 0, 1, 4, 5, 9, A.
- **Variables:** relative humidity is derived from observed temperature and
  dew point using the pipeline's own formula. Wind is m/s × 3.6. Rainfall is
  the depth over a P-hour period, compared with the sum of P model hours.
- **Outcome labels:** SUPPORTED, CONTRADICTED or MIXED, from pooled
  moving-block bootstrap intervals of |e_C4| − |e_baseline|.
- **Minimum sample:** stations with fewer than 500 matched hours are
  reported but not pooled.

## Run (two separate, logged, resumable steps)

```bash
python research/stage5_observational_validation/station_matching.py
python research/stage5_observational_validation/discover_sources.py
python -u research/stage5_observational_validation/evaluate_frozen_model.py --step gate6    > results/logs/gate6_run.log 2>&1
python -u research/stage5_observational_validation/evaluate_frozen_model.py --step evaluate > results/logs/evaluate_run.log 2>&1
```

Always run `python -u` with output redirected to a file (never through a
buffering pipe) and run the steps alone, with the machine awake. Gate 6
checkpoints live in `results/checkpoints/`; an interrupted Gate 6 resumes
and reuses every fold that re-validates against the current Stage 4D
files.

## Run record (2 Oct 2026)

- A first attempt on 30 Sep left no trace (in-memory only, output buffered,
  process ended by an OS power-off). The scripts were then made observable
  and resumable (`gate6.py`), with no change to the frozen model, features,
  folds or thresholds.
- Gate 6: folds 6142, 6198 and 6246 were verified in the first run; the run
  was stopped by the agent harness's background time limit during fold
  6253; the resume reused the three checkpoints and verified 6253.
  **4 folds x 15 hashes = 60/60 identical to Stage 4D.**
- The first evaluation attempt was stopped by hand: timezone-aware day
  labels made the bootstrap run on object arrays (hours instead of
  seconds). The fix (integer day codes, per-station groups prepared once)
  is tested to reproduce the original implementation's intervals exactly.
  The aborted log is kept as `results/logs/evaluate_run_ABORTED_slow_bootstrap.log`.
- No Modern Standby, shutdown or Python crash occurred during any of the
  runs that produced the results.

Raw observations live in `data/raw/observations/` (gitignored). The
committed outputs are in `results/`: `observation_source_manifest.json`,
`station_inventory.csv`, `station_matching.csv`,
`observation_qc_report.json`, `stage5_results.json`,
`station_level_results.csv`, `region_level_results.csv`,
`seasonal_results.csv`, and `provenance.json`.

## Key limitations

- **No PRIMARY station:** no ISD station lies inside a Stage 4 Panchayat
  polygon. All comparisons are the nearby diagnostic set: stations 6–17 km
  from the matched Panchayat centroid, at towns, observatories and airports.
- **Coverage:** 4 stations, 3 regions (coastal, central plateau, eastern
  plateau). The Western Ghats, northern plains and southern plateau have none.
- **SYNOP sampling:** reports are 3-hourly and incomplete. Karwar reports only
  at 03–12 UTC, so its comparisons are daytime-only.
- **Rainfall:** every rain-bearing ISD record at these stations (1,489 of
  1,678) carries condition code 3 ("begin accumulated period"), which the
  pre-declared rule excludes. The 93 usable records are all zero or trace,
  so there are no wet periods to evaluate and the outcome is INSUFFICIENT.
  Whether the condition-3 depths are usable is an open decision; any change
  must be a new, labelled, post-hoc analysis.
- **Dominant station:** Mangalore (hourly METAR) supplies about 72 % of the
  matched hours; per-station results are reported alongside pooled ones.
- **Route to a primary set:** KSNDMC (Panchayat-level gauges) and IMD DSP
  data, which require a request made by the user.
