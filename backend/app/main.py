import os
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import api_errors, config_check, observability
from app.model import artifacts

# Fail fast and clearly (before torch / ultralytics are imported) if REQUIRE_DISEASE_MODELS is set and artifacts are missing.
observability.configure_logging()
_ARTIFACTS = artifacts.enforce_startup()
_ENV_CHECK = config_check.check_environment()

from app.downscaling.routes import router as downscaling_router
from app.downscaling.strategy import strategy_status
from app.geospatial import service as geo_service
from app.geospatial.routes import router as geospatial_router
from app.routes.detect import router
from app.weather import service as weather_service
from app.weather.routes import router as weather_router

observability.log_event("startup_checks", disease_models_present=_ARTIFACTS["present"], disease_models_expected=_ARTIFACTS["expected"],
                        disease_models_missing=_ARTIFACTS["missing"], strict_startup=_ARTIFACTS["strict_startup"],
                        environment=_ENV_CHECK["environment"], config_errors=_ENV_CHECK["errors"], production_gaps=_ENV_CHECK["production_gaps"],
                        level="warning" if (_ENV_CHECK["errors"] or _ENV_CHECK["production_gaps"] or not _ARTIFACTS["ready"]) else "info")

IS_PRODUCTION = os.getenv("APP_ENV", "").strip().lower() == "production"

app = FastAPI(
    title="CropAI API",
    description="Real-time crop disease detection using YOLO + ResNet18 + Grad-CAM, "
                 "plus CropCast block-to-panchayat weather downscaling (deterministic baseline)",
    version="1.1.0"
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Read comma-separated origins from env var, e.g.:
#   ALLOWED_ORIGINS=https://cropai.vercel.app,https://crop-ai-app.vercel.app
# Falls back to wildcard if not set (dev mode). Set ALLOWED_ORIGINS in production.
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")

if _raw_origins.strip() == "*":
    allow_origins     = ["*"]
    allow_credentials = False          # credentials=True is incompatible with "*"
    if IS_PRODUCTION:
        observability.log_event("cors_wildcard_in_production", level="warning",
                                hint="set ALLOWED_ORIGINS to the frontend origin(s)")
else:
    allow_origins     = [o.strip().rstrip("/") for o in _raw_origins.split(",") if o.strip()]
    allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins     = allow_origins,
    allow_credentials = allow_credentials,
    allow_methods     = ["GET", "POST", "OPTIONS"],
    allow_headers     = ["*"],
    expose_headers    = ["X-Request-ID"],
    max_age           = 600,           # cache preflight for 10 min
)

api_errors.register(app)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Request id + one structured log line per request (path only: no query string, headers or body)."""
    rid = observability.new_request_id(request.headers.get("x-request-id"))
    token = observability.request_id_var.set(rid)
    t0 = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:  # noqa: BLE001 -- last-resort handler: generic body, details only in server logs
        observability.log_event("unhandled_exception", level="error", path=request.url.path, method=request.method,
                                exc_type=type(exc).__name__)
        observability.logger.error("unhandled exception", exc_info=True, extra={"event": "unhandled_exception_trace", "fields": {"path": request.url.path}})
        response = api_errors.respond(500, "Something went wrong on our side. Please try again.")
    latency_ms = round((time.perf_counter() - t0) * 1000)
    response.headers["X-Request-ID"] = rid
    if request.url.path not in ("/health",):                       # the keep-alive ping would drown real signals
        observability.log_event("http_request", method=request.method, path=request.url.path, status=response.status_code,
                                latency_ms=latency_ms, level="warning" if response.status_code >= 500 else "info")
    observability.request_id_var.reset(token)
    return response


app.include_router(router, prefix="/api")

# ── CropCast: weather + geospatial + deterministic baseline downscaling ─────────
app.include_router(weather_router,      prefix="/api/v1/weather",     tags=["weather"])
app.include_router(geospatial_router,   prefix="/api/v1/geospatial",  tags=["geospatial"])
app.include_router(downscaling_router,  prefix="/api/v1/downscaling", tags=["downscaling"])


@app.get("/")
async def root():
    body = {"status": "CropAI API running 🌱", "docs": "/docs"}
    if not IS_PRODUCTION:
        body["origins"] = allow_origins          # development convenience only; not disclosed in production
    return body


@app.get("/health")
async def health():
    """LIVENESS: the process is up and answering. Says nothing about weather. Used by UptimeRobot / Render health check."""
    return {"ok": True}


@app.get("/ready")
async def ready():
    """
    Three separate readiness answers (never conflated):

      application / weather  `ready` and `checks`: the process can serve weather. Checks only what this process controls
                             (configuration, seed geography, correction strategy); it does NOT call Open-Meteo, so an
                             upstream outage cannot remove the service from rotation. HTTP 503 only for a broken local
                             configuration.
      disease detection      `disease_detection_models`: present / expected / missing / wrong_size / ready. NOT part of
                             `ready` (weather must keep working without them), but `status` becomes "degraded" and the
                             detect endpoint answers 503 for any crop whose model file is absent. With
                             REQUIRE_DISEASE_MODELS=true the process refuses to start without them, so a running
                             instance in that mode always has disease_detection ready.
    """
    provider = weather_service.provider_status()
    strategy = strategy_status()
    checks = {
        "weather_provider_configured": provider["provider_known"],
        "geospatial_data_loaded": bool(geo_service.list_blocks()) and bool(geo_service.list_panchayats()),
        "correction_strategy_available": strategy["active_method"] == "baseline",
    }
    weather_ok = all(checks.values())
    disease = artifacts.status()
    env = config_check.check_environment()
    return JSONResponse(status_code=200 if weather_ok else 503, content={
        "ready": weather_ok,
        "status": "ok" if weather_ok and disease["ready"] else "degraded",
        "readiness": {"application": True, "weather": weather_ok, "disease_detection": disease["ready"]},
        "checks": checks, "weather": {**provider, "ready": weather_ok}, "downscaling": strategy,
        "disease_detection_models": {**disease, "affects_readiness": False},
        "configuration": {"environment": env["environment"], "errors": env["errors"], "production_gaps": env["production_gaps"]},
        "counters": observability.counters(),
    })
