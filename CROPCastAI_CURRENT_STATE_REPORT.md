# CropCastAi — Current State Report

**Audit date:** 2026-09-26  
**Scope:** Current checkout at `C:\crop-ai-app`; source, configuration names (secret values withheld), local data/output inventory, Git state, and local listening ports.  
**Method:** Read-only inspection of code/data/configuration and local listeners. No services, builds, or tests were run. The requested report file was created. Four frontend files appeared as modified in the working tree during this audit; their diffs were inspected but not edited by me.

## Executive Summary

CropCastAi is a React/Vite and FastAPI application combining an older crop-leaf disease demo/store with a newer CropCast weather foundation. The main CropCast experience is implemented as a dashboard, daily comparison view, and point map. It fetches a single block point forecast from Open-Meteo by default, then applies an elevation-based baseline to three seeded panchayat-like points. Temperature uses a fixed lapse-rate formula; rainfall, humidity, and wind use expressly uncalibrated heuristics. There is **no trained weather-downscaling model connected to the live pipeline and no CropCast agro-meteorological advisory engine**.

The repository now contains a meaningful research/data track: local ERA5 and ERA5-Land monthly files cover 2021–2023; a small June 2023 ERA5-Land pilot has normalized CSVs, training pairs, and baseline metrics; and separate LGD, historical spatial proxy, Copernicus DEM, and grid-linkage artifacts exist. The multi-year raw acquisitions are not yet built into a processed multi-GP dataset, evaluated from that dataset, or consumed by the live app. The pilot metric reports worse temperature RMSE for the elevation-adjusted baseline than for the block-as-is comparator, against an ERA5-Land reanalysis proxy (not observations).

CropAI has local ResNet18 weights for nine configured crops, a YOLOv8n weight file, classification/Grad-CAM code, and a static treatment/catalog UI. Inference and classifier accuracy were not verified. The UI advertises Wheat, which has no backend model configuration. Product, dosage, effectiveness, ratings, cart, and checkout behavior are frontend-only demo data; checkout displays a simulated order alert and does not process payment. Current uncommitted home-page UI rebrands the product as CropCastAI, adds Weather Intelligence/Crop Health cards, and labels advisory in development; it also retains unsupported/inconsistent hero stats (“94% Accuracy*”, “10 Crops”) and a “See all 12” product link despite 15 catalog records.

No app listener was found on ports 5173 or 8000 during inspection. Therefore frontend rendering, API responses, live Open-Meteo access, model inference, build, and tests are **NOT VERIFIED** at runtime. Do not present the system as completed SIH26074 functionality.

## Architecture

```text
USER
 ↓
React/Vite SPA (frontend/src/App.jsx)
 ├─ CropAI home, detect, result, medicines and cart UI
 └─ CropCast tab: dashboard / panchayat table / point map
 ↓ /api proxy in development
FastAPI (backend/app/main.py)
 ├─ CropAI multipart image routes
 ├─ CropCast in-memory geospatial seed records
 ├─ weather provider selection and normalization
 └─ block-to-panchayat baseline adjustment
 ↓
Sources
 ├─ Open-Meteo forecast API (live default); mock fallback on exceptions
 ├─ seeded demo coordinates and elevation values
 └─ separate offline ERA5/ERA5-Land research artifacts (not runtime-connected)
 ↓
UI results: diagnosis / static treatment info / static products;
 CropCast comparison bars, daily table, point markers
```

There is no database, persistence layer, or authentication in the inspected backend. The CropCast location catalog is in-memory. Research modules under `research/` are isolated from the API. Vite proxies `/api` to `http://localhost:8000`; frontend uses `VITE_API_URL` when supplied. No Dockerfile, Compose file, notebook, or Render manifest was found in the listed repository files; `vercel.json` exists for frontend deployment configuration.

## Feature Status

Status meanings: **FULLY IMPLEMENTED** means code path is present, not that it was live-tested; **PARTIALLY IMPLEMENTED** means only part of the advertised capability exists; **DEMO / MOCK** means seeded or static demonstration behavior; **RESEARCH / EXPERIMENTAL** means offline research artifact/code; **PLANNED / NOT IMPLEMENTED** means no implementation found; **NOT VERIFIED** means runtime behavior was not established.

| Feature | Status | Relevant implementation / actual behavior | Data and dependencies / limitations |
|---|---|---|---|
| A. Crop disease detection | PARTIALLY IMPLEMENTED | `POST /api/detect` calls image validation and `predict_image`. | Local Python/PyTorch/torchvision/OpenCV/Ultralytics/Pillow and weights; end-to-end inference NOT VERIFIED. |
| B. Crop selection | PARTIALLY IMPLEMENTED | Frontend has 10 entries including Wheat; backend has 9 configured crops. | `frontend/src/App.jsx`; `backend/app/model/predict.py`. Wheat selection returns an unsupported-crop result. |
| C. Image upload | PARTIALLY IMPLEMENTED | Browser file picker/drop and camera capture UI; backend accepts JPEG/PNG/WebP MIME types and decodes with Pillow. | No backend upload size limit found; camera requires browser/device permissions. |
| D. Leaf detection / YOLO | PARTIALLY IMPLEMENTED | `YOLO("yolov8n.pt")` runs on a green-filtered image; largest detected box is selected; if no boxes, full image is used. | Generic YOLOv8n weights; no crop-specific leaf detector/config or class filtering found. YOLO behavior NOT VERIFIED. |
| E. Disease classification / ResNet | PARTIALLY IMPLEMENTED | Per-crop ResNet18 with crop-specific output classes; top three softmax scores returned. | Nine `.pth` files exist. Training script exists; no per-weight verified evaluation metadata found. |
| F. Grad-CAM | PARTIALLY IMPLEMENTED | Hooks ResNet `layer3[-1]`, backpropagates selected class, overlays heat map, restricts by detector mask when available. | Implemented for visualization; explanation quality NOT VERIFIED. |
| G. Disease diagnosis | PARTIALLY IMPLEMENTED | Highest class is accepted at confidence ≥60%; healthy predictions have a special >88% branch; top predictions returned. | Labels depend on trained class order matching config; no measured diagnostic accuracy. |
| H. Treatment recommendations | DEMO / MOCK | Static disease descriptions, severity and remedy text in frontend; recommendations selected by predicted display label. | No weather, agronomy knowledge service, or server-generated treatment logic. Some label mismatch risk (e.g. `Panama_Disease` versus `Panama Wilt`). |
| I. Medicine store | DEMO / MOCK | Static catalog of 15 product records with search/filter/sort. | No product API or inventory service. Ratings, review counts, prices, effectiveness and stock are hardcoded. |
| J. Product details | DEMO / MOCK | Modal displays static active ingredient, formulation, dosage, frequency, PHI, safety level and price. | User-facing claims have no evidence/source model in the app; not verified as current product labeling. |
| K. Cart / purchase flow | DEMO / MOCK | In-memory React cart; add/remove/quantity/subtotal/delivery display. Buttons show an alert claiming order placed. | No order backend, payment processor, checkout, or persistence; the alert itself says payment integration is needed. |
| L. CropCast dashboard | PARTIALLY IMPLEMENTED | Loads one seeded block, three forecasts, comparison bars, source/method badges. | Live API and browser behavior NOT VERIFIED. |
| M. Block weather | PARTIALLY IMPLEMENTED | One forecast requested at block centroid. | Open-Meteo default, mock on provider exception; one block only. |
| N. Panchayat weather | DEMO / MOCK | Three seeded IDs/points; table compares block and adjusted forecast by day. | Not official panchayat entities or verified administrative centroids. |
| O. Weather downscaling | PARTIALLY IMPLEMENTED | Reuses one coarse/block forecast and adjusts by elevation. | Baseline only; rainfall/humidity/wind coefficients uncalibrated; no statistical/ML model. |
| P. Rainfall | PARTIALLY IMPLEMENTED | Open-Meteo `precipitation_sum`; baseline multiplies by elevation heuristic and clamps factor to 0.5–1.6. | Not locally calibrated. |
| Q. Maximum temperature | PARTIALLY IMPLEMENTED | Open-Meteo daily max; adjusted with lapse-rate temperature shift. | Forecast is at a single coarse point; no local validation. |
| R. Humidity | PARTIALLY IMPLEMENTED | Open-Meteo daily mean RH; baseline adds elevation-dependent percentage-point shift. | Placeholder coefficient. |
| S. Wind | PARTIALLY IMPLEMENTED | Open-Meteo daily maximum 10 m wind speed; baseline applies elevation multiplier. | Placeholder coefficient. |
| T. Weather map | PARTIALLY IMPLEMENTED | Leaflet map with block/panchayat circle markers and variable-scaled colors. | Point markers only, no raster/grid/contours; OpenStreetMap tile network required. |
| U. Open-Meteo | PARTIALLY IMPLEMENTED | HTTP request to public forecast API; normalized daily schema. | Network dependency; current request was not tested. Not IMD/government data. |
| V. Mock fallback | DEMO / MOCK | Deterministic-pattern provider is returned on Open-Meteo exception and marks `is_mocked=true`, `source=mock`. | Values are synthetic; Python `hash()` may vary across process launches, so exact values are not guaranteed across restarts. |
| W. ERA5 / ERA5-Land research pipeline | RESEARCH / EXPERIMENTAL | Acquisition, archive handling, normalization, pairing, spatial linkage and multi-GP build code exist. | Not imported by live API. Raw 2021–2023 monthly files exist; full multi-GP processed build output absent. |
| X. Evaluation | RESEARCH / EXPERIMENTAL | Pilot MAE/RMSE JSON exists; evaluation compares block-as-is and lapse-rate temperature to reanalysis proxy. | Not station ground truth; not an ML validation result. |
| Y. ML weather-downscaling model | PLANNED / NOT IMPLEMENTED | No weather model trainer, checkpoint, loader, or inference path found. | Schema permits `ml_corrected` literal, but service always emits `baseline`. |
| Z. Agro-meteorological advisory | PLANNED / NOT IMPLEMENTED | No CropCast risk/advisory engine found. | Static CropAI disease text is not a weather-driven advisory. |

## Disease Detection

**MODEL:** Crop-specific image classifier weights, loaded lazily and cached per crop.  
**ARCHITECTURE:** ResNet18; final fully connected layer replaced for each crop class count. `load_model()` uses `torchvision.models.resnet18(pretrained=True)` before loading the local state dict. Training script uses ImageNet ResNet18 weights and a final linear layer.  
**WEIGHTS:** `backend/app/model/{tomato,potato,pepper,banana,cotton,mango,onion,rice,sugarcane}_model.pth` exist (about 44.8 MB each); `backend/yolov8n.pt` exists. Nine configured classifiers, despite source comments/UI implying ten.  
**SUPPORTED CROPS:** Tomato, potato, pepper, banana, cotton, mango, onion, rice, sugarcane. Wheat is shown in the UI but absent in `CROP_CONFIG` and `/api/crops`.  
**SUPPORTED CLASSES:** Config contains 30 class labels total across crops (healthy plus disease labels); 21 are disease labels by per-crop config count. These are the only supported outputs; they are not a complete disease taxonomy.  
**INPUT:** multipart `crop` plus image file; accepted backend MIME values JPEG/JPG/PNG/WebP. Pillow converts to RGB. Frontend accepts any `image/*` before request.  
**VALIDATION:** HSV green pixel ratio must exceed 4%; otherwise response is `rejected`. This is a hand-coded color heuristic, not a learned quality check.  
**INFERENCE:** Resize to 224×224, ImageNet normalization, CPU `torch.load(..., map_location="cpu")`, softmax, top-three classes. Confidence gate is 60%, except a `healthy` best class above 88% returns success. Error and rejected payloads are returned from prediction as ordinary JSON (the unsupported-crop `status:error` path is not an HTTP validation error).  
**YOLO:** Generic `yolov8n.pt` inference runs on a green-filtered image. The code selects the largest returned box without checking class identity. If YOLO finds no boxes, it falls back to the full image. This means a displayed box is not proof of a crop-specific trained leaf detector. There is also a green-ratio prefilter before YOLO.  
**EXPLAINABILITY:** Grad-CAM uses the last `layer3` block; overlay is generated after classifier inference and returned base64 encoded with a boxed image. Explainability output is a visualization, not proof of causal reasoning.  
**DIAGNOSIS/TREATMENT:** Class label and confidence come from the classifier. Description, severity and remedies come from frontend `DISEASE_INFO` static maps. Label normalization replaces underscores with spaces and tries case-insensitive lookup. Product matching is another static map; unseen/mismatched labels may have no disease detail/products.  
**FAILURE HANDLING:** Route validates MIME and catches unreadable image errors. Color gate rejects; low confidence rejects; no surrounding route-level catch for missing/corrupt weight or model import/inference errors was found. Runtime behavior is NOT VERIFIED.  
**ACCURACY:** NOT VERIFIED. No classifier benchmark/holdout metric artifact was found. `backend/train_model.py` can print validation accuracy and save metadata when run, but no current crop metadata JSON was found. Training script is not evidence of current accuracy.  
**CURRENT STATUS:** PARTIALLY IMPLEMENTED; cannot claim it currently runs successfully without a local inference check. Avoid disease inference as an untested live-video dependency.

## Medicine & Treatment

The store has **15 static products** (`m01`–`m15`), with categories including fungicides, fungicide/bactericide combinations, bactericides, insecticide/vector control, and bio-pesticide; types include `chemical`, `organic-approved`, and `organic`. Product records contain hardcoded crops, disease mappings, indicative price/MRP, stock, rating/reviews, “effectiveness”, active ingredient, formulation, dosage, frequency, pre-harvest interval and safety level.

Disease result UI selects remedy text from static `DISEASE_INFO` and recommended product IDs from static `DISEASE_MEDICINES`. It may rank products by the hardcoded effectiveness value. This is not backend or model generated. Product details are a modal, not a separate route. Cart state is local React state and is not persisted. “Buy Now” and “Checkout” call `alert()` and clear/close UI state; source text explicitly says to integrate Razorpay/PayU for real payment. There is no stock reservation, order record, payment, shipping or backend integration.

Dosage and safety information are displayed as if usable instructions, but the repository provides no source synchronization or verification. The UI includes a general disclaimer to follow label instructions and local guidance. Do not present product claims, effectiveness percentages, ratings, stock, shipping or checkout as live/commercially validated.

## CropCast

**Flow:** Dashboard calls geospatial block and panchayat endpoints plus the block-wide downscaling endpoint. The backend fetches one block forecast, applies the same result to each panchayat using seeded elevations, and returns daily adjusted estimates. The frontend renders first-day bars, a multi-day comparison table, or colored point markers.

**Coverage/geography:** One block (`BLOCK-DEMO-001`), three panchayat placeholders (`PANCH-DEMO-001..003`). Block point 13.40, 77.73; Panchayat A 13.370, 77.680; B 13.470, 77.500; C 13.500, 77.900. Coordinates are plausible locations near the Nandi Hills area, but names/IDs are generic placeholders and do not map to official records/boundaries. Elevations are 929 m, 1,393 m, 741 m and 850 m, respectively (seed values sourced during development from Open-Meteo elevation lookup per comments; not dynamically resolved per panchayat at runtime). No polygon/boundary data in the live app.

**Forecast source/variables:** Open-Meteo `api/v1/forecast` at block lat/lon, daily: `temperature_2m_max`, `temperature_2m_min`, `precipitation_sum`, `windspeed_10m_max`, `relative_humidity_2m_mean`; timezone auto; request horizon 1–16 days (default seven at API, dashboard asks three days, detail five, map one). Provider returns its snapped coordinates/elevation when present, and reports source and mock flag. Resolution of the Open-Meteo underlying model is not declared by this app and is NOT VERIFIED here. There is no selectable date/scenario or historical playback.

**Downscaling mathematics:** For elevation difference `Δz = panchayat_elevation − block_elevation`:

- Temperature min/max: `T_p = T_block − 0.0065 × Δz` °C.
- Rain: `P_p = max(0, P_block × clamp(1 + 0.03 × Δz/100, 0.5, 1.6))` mm.
- Humidity: `RH_p = clamp(RH_block − 0.5 × Δz/100, 0, 100)` percentage points.
- Wind: `W_p = max(0, W_block × (1 + 0.02 × Δz/100))` km/h.

Only the temperature lapse rate is presented as an established physical constant. Other magnitudes are illustrative and not calibrated against local observations. For A relative to the seeded block, this produces approximately −3.0°C, +13.9% rain factor, −2.3 percentage points humidity, +9.3% wind factor. These are outputs of the formula, not validated local forecast skill.

**ML/checkpoints:** **NO TRAINED WEATHER-DOWNSCALING MODEL IS CURRENTLY CONNECTED TO THE LIVE CROPCast PIPELINE.** No weather checkpoint, architecture, training loop or inference loader found under backend. `DownscalingMethod` schema allows `ml_corrected`, but service hardcodes `method="baseline"`.

**Visualization:** Comparison bars, daily table with deltas and adjustment explanation, plus Leaflet point map. Map has no weather grid, polygon fill, interpolation or raster layer. Source/method badges show live/mock and baseline/ML label. The UI displays demo-data and not-ML warnings.

## Weather Data

| Source | Product / variables | Resolution / time | Purpose | Integration state |
|---|---|---|---|---|
| Open-Meteo | Forecast API: daily min/max 2 m temperature, daily precipitation sum, daily mean RH, daily max 10 m wind speed; elevation metadata can be returned. | App requests 1–16 forecast days; underlying spatial resolution not specified by app, NOT VERIFIED. | Live CropCast block-point input. | Implemented in provider; external call and current availability NOT VERIFIED. Failure falls back to mock. |
| Mock provider | Synthetic temperature/rain/RH/wind pattern derived from coordinates and current date. | Requested number of daily records; not meteorological resolution. | Offline/test fallback. | Implemented, explicitly marked mocked. Never real weather. |
| ERA5 | ERA5 single-level reanalysis, 0.25°; hourly; 2021–01 through 2023–12 monthly archive files. t2m, d2m, tp, u10, v10. | Native ERA5 0.25°; hourly; 36 months. | Coarse research inputs in Phase 2D multi-GP dataset plan. | Files exist; research code only. Not connected to live app. |
| ERA5-Land | ERA5-Land reanalysis, 0.1°; hourly; 2021–01 through 2023–12 monthly archive files, plus separate June 2023 pilot. Same base variables; RH derived, wind speed derived. | Native 0.1°; hourly; 36 months for multi-GP archive; pilot 3 days June 2023. | Reanalysis proxy target / pilot evaluation. | Files exist. Pilot is processed; multi-year raw downloads are not built into the declared Parquet output. Not connected to live app. |

No IMD or station-observation source was found in live runtime or the examined research chain. All ERA5 products are reanalysis, not observations or forecasts.

## Dataset Status

| Location | Current contents / inventory | State and caveats |
|---|---|---|
| `data/raw/era5_land/multi_gp/` | 36 monthly primary ERA5-Land NetCDF files (2021–2023), plus ZIP copies. | Downloaded. Count indicates 12 files per year; raw monthly archives. Not shown as normalized/model input output. |
| `data/raw/era5/multi_gp/` | 36 months (2021–2023), with primary NetCDF, split accumulation member, and ZIP per month. | Downloaded. Code documents instant/accum ZIP members. Raw monthly archives. |
| `data/raw/era5_land/` | June 2023 pilot NetCDF and ZIP; Yelandur June 2023 NetCDF and ZIP. | Local files; pilot ingestion outputs point to `era5_land_pilot_202306.nc`. |
| `data/processed/weather/` | `.gitkeep` plus block and three panchayat CSVs (~33–34 KB each). | Pilot processed; hourly records from 2023-06-01 to 2023-06-03. Four locations. |
| `data/training/training_pairs.csv` | ~199 KB; columns include timestamp, coarse/fine values, coordinates/elevation, variable, unit, source note. | Pilot pairs exist; explicitly labeled reanalysis proxy, not observation. 216 temperature samples in metrics (per other variables sample sizes 213–216). |
| `data/evaluation/baseline_metrics.json` | ~963 bytes. | Pilot metrics exist, see Evaluation. Not multi-year transfer evaluation. |
| `data/raw/elevation/` | Four Copernicus DSM GeoTIFF tiles and a tile list (~170 MB total). | Research source data. Separate Yelandur context layer; not CropCast live elevations. |
| `data/raw/datameet/` | Karnataka GeoJSON (~86.5 MB) and provenance manifest. | Historical village boundaries source; not current live panchayat boundaries. |
| `data/raw/lgd/` | Karnataka LGD component CSVs and `.7z` archives (~207 MB). | Untracked local download; data identity source, not integrated into CropCast seed. |
| `research/admin_identity/` | 12 Karnataka Gram Panchayat identity records for Guledagudda, Bagalkot. | Research identity data only, no coordinates/boundaries; distinct from Yelandur proxy artifacts and live placeholder points. |
| `research/spatial_proxy/yelandur_spatial_proxy.json` | 12 GP records; 10 complete geometries, one partial, one unavailable per artifact docs. | Historical village-union geometry proxy, not current GP boundaries; not live. |
| `research/elevation/yelandur_elevation.json` | Copernicus DEM GLO-30 zonal stats (30 m nominal), with proxy coverage caveats. | Research-only; does not establish elevation improved weather prediction. |
| `research/era5_linkage/yelandur_era5_linkage.json` | Grid link metadata for 12 GP proxies; distinct ERA5-Land grid-cell coverage described in manifest. | Spatial linkage metadata, not prediction. |
| `data/training/yelandur_multi_gp.parquet` | Not found. | Multi-year acquisition exists, but processed dataset build output is absent. |

The latest multi-GP acquisition code requests 36 months for each product (72 monthly product requests before caching), but the local file inventory alone cannot prove every NetCDF is scientifically intact/openable. File names/counts are consistent with all months being present. Data schema and monthly response handling are described in `research/multi_gp/acquire.py`. The pilot processed outputs are a separate smaller dataset.

## ML / Downscaling

There is no trained weather model, model architecture, model training dataset from the 2021–2023 downloads, loss function, trained checkpoint, backend loader, or frontend ML prediction path. The requested multi-GP dataset builder includes pairing/split logic, but no Parquet output is present and the builder explicitly says it trains no model. The live endpoint always returns `method="baseline"`.

The CropAI disease classifier is a separate image ML path, not the weather model. It has local weights and a training script; no verified classifier evaluation artifact was found. The generic YOLO weights are separate from per-crop ResNet weights.

## Research Pipeline

| Component | Purpose / inputs | Outputs observed or expected | Status | Used by live system? |
|---|---|---|---|---|
| `research/era5_land/acquire.py` | Requests small June 2023 ERA5-Land pilot using CDS credentials. | `data/raw/era5_land/era5_land_pilot_202306.nc` and ZIP copy observed. | RESEARCH; local pilot file present. | NO |
| `research/era5_land/archive.py` | Detect/extract CDS NetCDFs returned as ZIP archives. | Normalized files and retained ZIP behavior. | Code present; NOT run during this audit. | NO |
| `research/pipeline/normalize.py` + script | NetCDF variables → per-point hourly CSVs, unit conversions, RH/wind derivation and precipitation deaccumulation. | Four pilot weather CSVs observed. | Pilot outputs present. | NO |
| `research/pipeline/training_pairs.py` + script | Join hourly block coarse values to panchayat proxy values. | `data/training/training_pairs.csv` observed. | Pilot pairs present. | NO |
| `research/pipeline/baseline_eval.py` + script | Evaluate block-as-is and production lapse-rate temp formula vs reanalysis proxy. | `data/evaluation/baseline_metrics.json` observed. | Pilot evaluation present. | NO |
| `research/admin_identity/` | Retrieve/load LGD administrative identity hierarchy. | 12 real GP records for Guledagudda, Bagalkot; raw LGD components downloaded. | Research artifact; identity only. | NO |
| `research/spatial_proxy/` | Match constituent village polygons to GP identity and build union geometry. | Yelandur spatial proxy JSON; 10 complete, 1 partial, 1 unavailable per artifact. | Research; historical village boundaries with documented gaps/positional limits. | NO |
| `research/elevation/` | DEM zonal elevation context for existing proxy geometries. | Yelandur elevation JSON with 30 m Copernicus DSM stats. | Research; context only. | NO |
| `research/era5_linkage/` | Link GP proxy geometry/centroid to ERA5-Land and ERA5 grids. | Yelandur linkage JSON, 4×5 0.1° ERA5-Land linkage area and grid metadata. | Research; links are not downscaled predictions. | NO |
| `research/multi_gp/acquire.py` | Monthly ERA5 and ERA5-Land reanalysis acquisitions, 2021–2023. | Raw monthly archives for both products observed. | Acquisition evidence present; scientific integrity not independently validated here. | NO |
| `research/multi_gp/pairing.py`, `splits.py`, `build.py` | Build coarse/fine spatial-transfer pairs and leakage-safe splits. | Expected `data/training/yelandur_multi_gp.parquet` and manifest not found under the data output; research manifest artifact not present in directory listing. | Code is research/experimental; dataset build output NOT VERIFIED / absent. | NO |
| ML weather training | Would train an ML downscaler. | No weather model trainer/checkpoint found. | NOT IMPLEMENTED. | NO |

The research geography differs across stages (e.g. Guledagudda LGD identity records versus Yelandur spatial/elevation/linkage artifacts) and neither is the live demo’s Nandi Hills-area seeded points. Do not imply these layers are one already-joined production dataset.

## Evaluation

Only one evaluation artifact was found: `data/evaluation/baseline_metrics.json`. It reports pilot metrics against ERA5-Land reanalysis proxy targets. `n` is paired sample count. No trained ML model was compared.

| Variable / method | n | MAE | RMSE | Interpretation / limitation |
|---|---:|---:|---:|---|
| Dewpoint, block-as-is | 216 | 0.3381 °C | 0.4553 °C | Proxy comparison; not direct observation. |
| Rainfall, block-as-is | 213 | 0.083 mm | 0.3544 mm | Proxy comparison; sparse/zero rainfall can dominate interpretation. |
| Relative humidity, block-as-is | 216 | 2.2857 pp | 3.211 pp | Proxy comparison. |
| Temperature, block-as-is | 216 | 0.632 °C | 0.7738 °C | Comparator. |
| Temperature, elevation lapse-rate baseline | 216 | 1.1135 °C | 1.6454 °C | Worse RMSE/MAE than block-as-is in this pilot. |
| Wind speed, block-as-is | 216 | 0.8161 km/h | 1.0808 km/h | Proxy comparison. |

The pilot is only three days (June 1–3, 2023), with proxy reanalysis sampled at the project points. Even though per-variable `n` exceeds the code’s 30-sample reporting floor, it does not establish independent spatial/temporal generalization or real-world accuracy. No classifier metrics, multi-year held-out ML metrics, or production monitoring results were found. The multi-GP split code proposes spatial/temporal folds but there is no corresponding built dataset/model metric artifact in this checkout.

## Frontend

This is a state-switched React SPA, not a router-backed collection of URL routes. Current uncommitted UI labels the app CropCastAI and exposes Home, Weather Intelligence, Crop Health and Medicines (the internal state keys remain `cropcast` and `detect`). The result view is entered after detection; product detail is a modal; cart is a drawer/modal overlay. The landing page labels advisory “IN DEVELOPMENT,” which matches the absence of an advisory implementation. Pages/screens:

| Screen | Main elements / data | API calls | Limitations |
|---|---|---|---|
| Home | CropCastAI branded hero, product cards for weather/crop health/advisory, workflow graphic and legacy product promotions. | None identified. | Marketing/product positioning only; hero accuracy/crop/product-count claims are unsupported or inconsistent with code/data. |
| Detect | Crop selector, upload/drop or live camera, preview, staged progress UI, analyze button. | `POST /api/detect`. | UI has 10 crops vs backend 9; progress steps include artificial waits; browser camera permission and backend required. |
| Disease result | Label, confidence/top predictions, boxed image, Grad-CAM, static disease details/remedies and linked products. | Result from detect request only; no separate call. | All downstream advisory content is static; mismatch/unknown labels possible. |
| CropCast dashboard | Block header, elevation/coordinates, method/source badge, first-day comparison bars, variable buttons. | GET block, panchayats, block downscaled forecasts. | One demo block; automatic current forecast; no location/date choice. |
| Panchayat Weather | Select among three placeholders, multi-day block-vs-estimate table, deltas, coefficient explanation. | Same CropCast calls, requests five days. | Heuristic correction and seeded geography. |
| Weather Map | Leaflet point markers, popup values, variable color scale. | Same CropCast calls, requests one day. | OSM tiles external; no continuous/grid surface. |
| Medicines | Static 15-product catalog; filters/search/sorts, product cards, cart actions. | None. | Fake/indicative static business data. |
| Product detail | Modal with static product metadata, quantity and Buy/Add buttons. | None. | No actual order/payment. |
| Cart/checkout | In-memory items, subtotal/delivery display, alert and clear. | None. | No persistence/backend/payment. |

The frontend CropAI request uses `VITE_API_URL` or relative `/api`; CropCast uses the same env option and Vite proxy by default. Home/Detect/Result are distinct app states, not directly addressable routes.

## Backend & APIs

Authentication: none found. Database: none found. Geospatial data: in-memory seed. Persistence: none for crop uploads, cart, forecasts, or orders. CORS reads `ALLOWED_ORIGINS`, defaulting to wildcard origins with credentials disabled. CropCast weather has an external Open-Meteo dependency and a mock fallback.

| Method / path | Purpose and input | Output / source | Error handling / runtime status |
|---|---|---|---|
| GET `/` | Root status. | Status, docs path, allowed origins. | Code-defined; NOT VERIFIED live. |
| GET `/health` | Lightweight backend health. | `{"ok":true}`. | Code-defined; NOT VERIFIED live. |
| GET `/api/health` | CropAI health. | Status/message. | Code-defined; NOT VERIFIED live. |
| GET `/api/crops` | List configured crops/classes. | Config-derived crop names/classes. | Code-defined; excludes Wheat. NOT VERIFIED live. |
| POST `/api/detect` | Multipart form `crop`, `file`. | status, disease/confidence/top predictions and base64 imagery on success. | 400 for unsupported MIME/unreadable image; prediction can return rejected/error JSON; model exceptions may escape. NOT VERIFIED live. |
| GET `/api/v1/geospatial/blocks` | List blocks. | In-memory seeded block list. | 200 code path. NOT VERIFIED live. |
| GET `/api/v1/geospatial/blocks/{block_id}` | Block lookup. | Block record. | 404 unknown block. NOT VERIFIED live. |
| GET `/api/v1/geospatial/panchayats?block_id=` | Panchayat list, optional block filter. | In-memory records. | 200 code path. NOT VERIFIED live. |
| GET `/api/v1/geospatial/panchayats/{panchayat_id}` | Panchayat lookup. | Panchayat record. | 404 unknown ID. NOT VERIFIED live. |
| GET `/api/v1/weather/block/{block_id}/forecast?days=1..16` | Forecast at block centroid. | Normalized `PointForecast` with provider/source/mock flag and daily values. | 404 unknown block; Open-Meteo exceptions fall back to mock. NOT VERIFIED live. |
| GET `/api/v1/downscaling/{panchayat_id}/forecast?days=1..16` | One panchayat baseline forecast. | Block source, adjustment metadata, daily adjusted values. | 404 unknown panchayat; 500 broken parent block. Provider fallback applies. NOT VERIFIED live. |
| GET `/api/v1/downscaling/block/{block_id}/forecast?days=1..16` | Forecast estimates for block’s panchayats. | List of three `DownscaledForecast` records. | 404 unknown block. One block forecast is fetched/reused. NOT VERIFIED live. |

FastAPI’s default docs route `/docs` is advertised by root. No API endpoint exists for products, cart, checkout, advisories, ERA5 access, model training or model status.

## Runtime Status

| Check | Result |
|---|---|
| Frontend listener, port 5173 | Not listening at audit time. Frontend availability NOT VERIFIED. |
| Backend listener, port 8000 | Not listening at audit time. API health NOT VERIFIED. |
| Other active processes | Node and Python processes were observed, but process command-line inspection was access denied; association with this app NOT VERIFIED. |
| Frontend dependency directory | `frontend/node_modules` exists. Exact package health/build NOT VERIFIED. |
| Backend runtime dependencies | requirements files exist; installation/import status NOT VERIFIED. |
| Disease inference | NOT VERIFIED; no inference executed. |
| Open-Meteo reachability | NOT VERIFIED; no live call made. |
| Build status | NOT VERIFIED; no build run. |
| Test status | Test files exist; tests were not run, so pass/fail NOT VERIFIED. |

## Git / Development Status

- Branch: `main`; HEAD `1b6834a`, matching `origin/main` in the observed log.
- Latest commit: `1b6834a` (2026-09-22), “Build CropCast AI Panchayat weather intelligence platform”. Earlier visible commits include frontend navigation/hamburger updates and deployment fixes.
- Working tree is not clean. Modified at the final check: `frontend/index.html`, `frontend/src/App.jsx`, `frontend/src/cropcast/CropCastDashboard.jsx`, `frontend/src/index.css`, `research/requirements.txt`. The four frontend diffs change branding/navigation/home presentation and CSS; no backend implementation was added by those diffs. Their change timing/author is NOT VERIFIED; I inspected but did not edit them. Untracked: this requested `CROPCastAI_CURRENT_STATE_REPORT.md`, `data/raw/lgd/`; `research/admin_identity/`, `research/elevation/`, `research/era5_linkage/`, `research/multi_gp/`, `research/spatial_proxy/`; and corresponding research tests. Preserve all such work/data.
- `.gitignore` excludes model weights, disease datasets, environment file, and raw/processed/training/evaluation data folders. The project contains substantial ignored local data and checkpoints, so `git status` does not enumerate the full runtime corpus.
- Major observed milestones: original CropAI UI/API/model pipeline; CropCast Phase 1 weather/provider/downscaling foundation; Phase 2A pilot ERA5-Land acquisition and evaluation; later research additions for LGD identity, historical spatial proxy, DEM elevation, ERA5 linkage, and multi-GP ERA5/ERA5-Land acquisition.

## Security & Configuration

- No actual secret values are reproduced here. Environment/configuration names used or expected in source include `VITE_API_URL`, `ALLOWED_ORIGINS`, `WEATHER_PROVIDER`, `CDSAPI_URL`, and `CDSAPI_KEY`. The backend `.env` contains `CDSAPI_KEY`; its value was not read or printed. Research configuration resolves CDS credentials from environment or a user `.cdsapirc` file.
- Open-Meteo is public and used without an API key; OSM map tiles are an external service. CDS acquisition requires credentialed access and accepted dataset terms; no acquisition was run as part of this audit.
- CORS defaults to `*` with credentials false unless `ALLOWED_ORIGINS` is configured. No authentication or authorization layer found.
- Upload route checks MIME type and Pillow decoding but no explicit payload/file size limit was found. It loads images and ML models into the backend process; inference exceptions are not wrapped in a user-safe route handler.
- No hardcoded credential was identified in the inspected application/configuration source. This is not a guarantee about every ignored/private local file; secret values were intentionally not printed.
- Product checkout UI has no payment integration despite “secure checkout” promotional copy; the modal alert itself names future payment integration. Do not treat it as an operational store.

## Current Limitations

- CropCast only contains one block and three generic demo locations; no official live administrative boundaries or IDs.
- The live app fetches one block forecast and derives three estimates; it does not ingest ERA5/ERA5-Land data at runtime.
- No trained weather-downscaling model or connected checkpoint; the existing baseline’s rainfall/humidity/wind coefficients are uncalibrated.
- Live forecast and map depend on external networks; Open-Meteo failures silently return clearly labeled mock data at the API/UI level.
- No weather-driven risk, agro-meteorological advisory, or crop recommendation service.
- 2021–2023 raw research downloads have not been turned into the expected multi-GP Parquet dataset in the inspected output tree; not used to train/evaluate a downscaling ML model.
- Existing pilot evaluation is three days of reanalysis proxy, not observations; lapse-rate correction performs worse than block-as-is on its temperature metric.
- CropAI model accuracy and live inference are not verified; Wheat UI selection has no backend model. YOLO is generic and has a full-image fallback.
- Treatment/product claims and commerce flows are static frontend demo data; no product backend, orders, inventory or payment.
- No database, authentication, persistence, or verified production runtime was found.

## Demo-Ready Features

| Screen | Action | Expected result | Data source | Important disclaimer |
|---|---|---|---|---|
| CropCast Dashboard | Start both services, open `http://localhost:5173`, click Weather Intelligence. | Block summary and bars comparing one block forecast with three adjusted estimates. | Open-Meteo if reachable; otherwise mock, identified by badge. | Placeholder geography; baseline not ML. Confirm live/mock badge before narration. |
| Panchayat Weather | Click detail; select Panchayat A; choose a variable. | Daily table, deltas, elevation/coefficient explanation. | Same block point forecast plus seeded elevation and code formula. | Rain/RH/wind factors are uncalibrated heuristics. |
| Weather Map | Click map, switch variables, click markers. | Colored block/panchayat point markers and popups. | API estimates plus OSM tiles. | Point visualization only; internet required for tiles. |
| Research-data inventory | Show filenames/manifest and the saved pilot metric JSON. | Evidence of raw reanalysis download, pilot preprocessing and proxy evaluation. | Local files under `data/` and `research/`. | Not runtime-integrated; reanalysis is not ground truth; pilot lapse adjustment scores worse. |
| Medicines UI | Browse filters/product details without purchase claims. | Static product cards and detail modal. | Hardcoded React arrays. | Demo catalog, unverified product information, no real checkout. |

**Do not rely on for recording without a separate local smoke verification:** CropAI inference (model load/YOLO/Grad-CAM and no accuracy evidence), any result described as validated diagnosis, real medication recommendations, checkout, official panchayat forecasts, a gridded high-resolution map, or an ML/advisory weather claim. The current app services were not running at audit time.

## Next Development Phase

These are technical milestones inferred from the gaps; none were implemented during this audit.

**PHASE A — Stabilization**

- Start the frontend/backend locally and verify health, all exposed API calls, CORS, environment configuration, and a browser walkthrough.
- Verify each CropAI model can load from the documented working directory; run representative images per configured crop; correct/disable the Wheat UI mismatch before presenting crop coverage.
- Record safe reproducible runtime instructions and distinguish forecast source from mock in every demo.

**PHASE B — Data integration**

- Validate every monthly ERA5/ERA5-Land file opens and has expected dates, variables, units, grid and completeness; produce a machine-readable inventory and checksums.
- Build the multi-GP Parquet dataset, inspect its manifest and effective independent spatial groups, and reconcile geography across LGD identity, proxy boundaries, DEM and ERA5 linkage.
- Make official-boundary vintage/coverage gaps explicit and keep reanalysis targets labeled as proxy data.

**PHASE C — ML downscaling**

- Define a baseline and feature/target dataset contract; avoid leakage with spatial and temporal splits already contemplated by `multi_gp/splits.py`.
- Train a modest model only after the dataset is built and inspected; version its code, parameters and checkpoint. Add a backend load/inference path and preserve baseline fallback/metadata.
- Do not promote a model until it beats a fair baseline on held-out data.

**PHASE D — Validation**

- Evaluate per variable and spatial group on held-out time/locations; compare against block-as-is and the existing physical baseline.
- Seek station observations or a clearly bounded independent validation source; do not label reanalysis agreement as observed local accuracy.
- Report sample counts, uncertainty, failure cases and geographic limits; add a reproducible evaluation artifact.

**PHASE E — Agro-meteorological intelligence**

- Specify crop/calendar/soil/stage inputs and validated risk logic with agronomic review; define advisory provenance, confidence, thresholds and safe wording.
- Integrate weather forecasts only after data source, temporal horizon and calibration are defensible. Separate risk scoring from treatment/product sales content.

**PHASE F — Productionization**

- Replace in-memory demo geography with maintained, licensed administrative data and persistent/versioned configuration.
- Add auth/access policy if needed, upload limits, model/data observability, API error handling, automated deployment/build/test checks, secret management, and real commerce only if product purchase is intended.
- Verify CORS origins, external-provider behavior, availability/cold-start requirements, and supported hardware/deployment resource needs.

## Evidence / Important Files

| Area | Evidence files |
|---|---|
| App structure / deployment | `frontend/src/App.jsx`, `frontend/src/main.jsx`, `frontend/vite.config.js`, `vercel.json` |
| CropAI API and classifier | `backend/app/main.py`, `backend/app/routes/detect.py`, `backend/app/model/predict.py`, `backend/app/model/model.py` |
| YOLO / Grad-CAM | `backend/app/model/leaf_detector.py`, `backend/app/model/grad_cam.py`, `backend/yolov8n.pt` |
| CropAI training / model files | `backend/train_model.py`, `backend/app/model/*_model.pth` |
| Store/treatment/cart UI | `frontend/src/App.jsx` (MEDICINES, DISEASE_INFO, DISEASE_MEDICINES, BuyModal, CartDrawer) |
| CropCast frontend | `frontend/src/cropcast/CropCastApp.jsx`, `CropCastDashboard.jsx`, `PanchayatWeatherPage.jsx`, `WeatherMapPage.jsx`, `api.js`, `useBlockData.js`, `shared.jsx` |
| CropCast providers/processing | `backend/app/weather/*`, `backend/app/geospatial/*`, `backend/app/downscaling/*` |
| Pilot/research docs and data | `CROPCAST_PHASE1.md`, `research/README.md`, `data/processed/weather/*.csv`, `data/training/training_pairs.csv`, `data/evaluation/baseline_metrics.json` |
| Multi-year research and linkage | `research/multi_gp/*`, `research/era5_linkage/*`, `research/elevation/*`, `research/spatial_proxy/*`, `research/admin_identity/*` |
| Dependencies/tests | `backend/requirements.txt`, `research/requirements.txt`, `backend/tests/*`, `research/tests/*`, `frontend/package.json` |
| Current state | Git branch/status/log; local listener check (5173/8000). |

## Final Status Matrix

| Component | Status | Basis |
|---|---|---|
| Frontend CropAI/CropCast screens | PARTIAL | Source and frontend dependencies present; not served/verified at audit time. |
| Crop disease classifier | PARTIAL | Nine configurations and weights exist; inference/accuracy NOT VERIFIED; UI advertises unsupported Wheat. |
| YOLO leaf localization | PARTIAL | Generic YOLOv8n path plus fallback; not a verified crop-specific leaf detector. |
| Grad-CAM display | PARTIAL | Implementation present; inference and explanation quality NOT VERIFIED. |
| Treatment / disease remedies | DEMO | Static frontend mappings and text. |
| Medicine store / cart / checkout | DEMO | Fifteen static products; local cart; alert-based fake order, no payment/backend. |
| CropCast geospatial records | DEMO | One block and three generic points in memory. |
| Open-Meteo provider | PARTIAL | Integration present; live network response NOT VERIFIED. |
| Mock weather fallback | DEMO | Implemented synthetic response explicitly marked mock. |
| CropCast baseline downscaling | PARTIAL | Formula works in code; coefficients partly heuristic and uncalibrated; runtime NOT VERIFIED. |
| ERA5/ERA5-Land monthly acquisition | RESEARCH | Raw 2021–2023 files present; file count/name evidence consistent with 36 months each. |
| Pilot processing/evaluation | RESEARCH | June 2023 CSVs, pairs, and proxy metrics present. |
| Spatial proxy / DEM / grid linkage | RESEARCH | Artifacts present, with historic/incomplete geography; not live-integrated. |
| Multi-GP processed dataset | NOT VERIFIED | Expected Parquet output not found; raw downloads found. |
| Trained weather downscaling | NOT IMPLEMENTED | No trainer/checkpoint/inference integration found. |
| Agro-meteorological advisory | NOT IMPLEMENTED | No CropCast advisory/risk engine found. |
| Backend/API runtime | NOT VERIFIED | Code routes present; port 8000 not listening and endpoints not queried. |
| Build/tests | NOT VERIFIED | Build/tests not run. |
| Production infrastructure | NOT VERIFIED | Deployment config/docs exist, but live deployment/production controls not inspected or verified. |
