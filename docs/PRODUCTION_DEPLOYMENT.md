# CropCastAI — Production deployment checklist (Render backend + Vercel frontend)

**ML weather correction is NOT deployed.** Panchayat forecasts use the deterministic baseline.
**Disease-detection models are a separate thing**: nine ResNet18 classifiers plus a YOLOv8n leaf detector. They have nothing
to do with weather downscaling and are the only model files the backend needs.

This repository has no `render.yaml`; the Render service is configured in the dashboard. Nothing below was applied to Render
from this repository — it is the checklist to apply and verify.

## 1. Required environment variables (Render → Environment)

| Variable | Value | Why |
|---|---|---|
| `APP_ENV` | `production` | hides dev-only output, enables the production checks |
| `ALLOWED_ORIGINS` | your Vercel origin(s), `https://…`, comma-separated | CORS; unset means `*` |
| `WEATHER_FALLBACK` | `error` | provider outage → HTTP 503/502, never synthetic numbers |
| `WEATHER_PROVIDER` | `open-meteo` (default) | |
| `REQUIRE_DISEASE_MODELS` | `true` | the process **refuses to start** if a model file is missing → Render keeps the previous deploy |
| `MODEL_ARTIFACT_BASE_URL` | URL of **your** artifact store folder | used by the build step only (section 3) |
| `MODEL_ARTIFACT_TOKEN` | token, only if the store is private | secret; never logged |
| `PORT` | injected by Render | the start command must bind it |
| `MODEL_DIR` | optional | default `backend/app/model`, resolved from the code (not the working directory) |
| `DOWNSCALING_METHOD`, `WEATHER_CACHE_TTL_S`, `WEATHER_FAILURE_COOLDOWN_S`, `MAX_UPLOAD_MB`, `LOG_LEVEL` | defaults are fine | |

`backend/.env.example` lists all of them with placeholders. Check a configuration without starting the server:
`cd backend && python -m app.config_check` (exit 1 if a value is invalid or, with `APP_ENV=production`, a requirement above is
missing; values are never echoed). Frontend (Vercel): `VITE_API_URL=<Render service URL>` (no trailing slash).

## 2. Disease-model artifact requirements

Required: 9 classifiers + 1 detector, listed with exact size and SHA-256 in `backend/model_manifest.json` (no URLs or
credentials in it).

| Crop | File | Size |
|---|---|---|
| tomato, potato, pepper, banana, cotton, mango, onion, rice, sugarcane | `<crop>_model.pth` | 44.8 MB each (≈ 403 MB total) |
| leaf detector | `yolov8n.pt` | 6.5 MB |

They are **git-ignored and have never been committed** (`*.pth`, `backend/*.pt`). Committing them is not appropriate: ≈ 410 MB of
binaries would be permanent in history, and there is no Git LFS setup. They are plain `state_dict`s, so they load with
`torch.load(..., weights_only=True)`, which the code now does explicitly (verified on all nine with PyTorch 2.9.1).

**Capacity:** loading all nine classifiers in one process measured ≈ 756 MB RSS (314 MB right after import, +442 MB for the
models), before request overhead. Use an instance with at least 1 GB RAM; a 512 MB plan will be killed by the platform.

## 3. Artifact installation procedure (no artifact store exists in this project yet)

The project has no object storage or artifact mechanism, and none was invented or contacted. The owner must host the ten files once
(any private HTTPS location that serves `<base>/<file name>`; for example a private release or bucket) and keep them versioned
(e.g. `…/models-v1/`). Then:

1. Upload the ten files from a machine that has them (this repo's working copy does): nothing in this repository uploads them.
2. Render build command: `pip install -r requirements.txt && python scripts/fetch_models.py`
   (root directory `backend`). The script downloads only what is missing/invalid, checks size **and SHA-256** against the manifest,
   writes to a temporary name and renames atomically; a mismatch installs nothing and fails the build. It never prints the URL or token.
3. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (no `--reload`).
4. Changing a model = new versioned folder + new `model_manifest.json` (`python scripts/fetch_models.py --write-manifest` on the
   machine holding the new files) + new `MODEL_ARTIFACT_BASE_URL`.

Useful commands: `python scripts/fetch_models.py --check` (presence/size only), `--verify` (SHA-256 of every file).

## 4. Startup and readiness verification

- With `REQUIRE_DISEASE_MODELS=true` an incomplete install **fails at startup** with a message naming the missing files
  (`DiseaseModelsMissingError … 0/9 models … tomato_model.pth …`) before torch is imported. The deploy fails; the previous deploy stays live.
- Without it the service starts, weather works, `/ready` reports `status: "degraded"`, and `POST /api/detect` answers a clear
  **503 `disease_models_unavailable`** for any crop whose file is absent (never a 500 from `torch.load`).
- `GET /ready` keeps three answers apart:
  `readiness.application`, `readiness.weather` (config, geography, correction strategy — it never calls Open-Meteo), and
  `readiness.disease_detection`, with `disease_detection_models` = `{present, expected, missing[], wrong_size[], available_crops[], ready}`.
  Top-level `ready` is application + weather only; it returns 503 only for a broken local configuration.
- `/ready` also exposes `configuration.production_gaps` (names only) so a misconfigured production instance is visible.

## 5. Render health endpoint

Health check path: **`/health`** (liveness, `{"ok": true}`). Do not use `/ready` as the platform health check: it reports
disease/weather detail and is meant for humans and smoke tests.

## 6. CORS

`ALLOWED_ORIGINS=https://<your-vercel-domain>[,https://<custom-domain>]`. Methods allowed: GET, POST, OPTIONS. Verify:
`curl -s -i -X OPTIONS "$API/api/v1/weather/block/BLOCK-DEMO-001/forecast" -H "Origin: https://<frontend>" -H "Access-Control-Request-Method: GET"`
must contain `access-control-allow-origin: https://<frontend>`; a foreign origin must not be echoed.

## 7. Weather fallback production setting

`WEATHER_FALLBACK=error`. Default (`mock`) returns an explicitly labelled mock forecast (`is_mocked: true`, `data_origin: "mock_fallback"`);
the frozen UI shows its "Sample data (offline)" chip, but production should not show synthetic weather at all.

## 8. Smoke tests (replace `$API`)

```bash
curl -s  $API/health                                  # {"ok":true}
curl -s  $API/ready | python -m json.tool             # status "ok"; readiness.* all true; disease_detection_models.present == 9
curl -s  "$API/api/v1/weather/block/BLOCK-DEMO-001/forecast?days=3"        # source "open-meteo", is_mocked false, data_origin "live_provider"
curl -s  "$API/api/v1/downscaling/PANCH-DEMO-001/forecast?days=3"         # method "baseline", provenance.correction_status "applied", ml_correction_enabled false
curl -s  $API/api/crops                               # 9 crops, no wheat
curl -s -o /dev/null -w "%{http_code}\n" "$API/api/v1/downscaling/NOPE/forecast"      # 404
curl -s -F crop=potato -F "file=@leaf.jpg;type=image/jpeg" $API/api/detect # status success|rejected (never a 5xx)
```
Pre-deploy, on the build machine: `python scripts/fetch_models.py --verify` and `python -m app.config_check`.

## 9. Rollback

1. Render dashboard → Deploys → redeploy the previous successful deploy (instant; models are part of that deploy's build).
2. Configuration regressions: restore the previous environment values (keep a copy of the working set).
3. Model regressions: point `MODEL_ARTIFACT_BASE_URL` at the previous versioned folder and restore the previous `model_manifest.json`
   from Git, then redeploy. Never overwrite a published artifact folder in place.
4. If a deploy fails at startup with `DiseaseModelsMissingError`, nothing is wrong with the running service: fix the artifact source and retry.

## 10. Known limitations

- The artifact store is not provided by this repository; the first deploy cannot succeed until the owner hosts the ten files.
- Memory: ≥ 1 GB needed (above); models are loaded lazily per crop and never evicted.
- Panchayats are demo placeholders; weather uses a deterministic, uncalibrated elevation baseline; no accuracy of Panchayat estimates has been measured.
- Disease-classifier accuracy has not been verified in this repository (no benchmark artifact); a synthetic test image produces arbitrary labels.
- `torchvision`, `torch`, `ultralytics` are unpinned; set the Python version explicitly on Render and consider pinning after a successful build.
- No authentication or rate limiting on the public API (the detect endpoint is CPU-heavy).
- Not verified: the live Render service itself (this repository cannot see its dashboard configuration).
