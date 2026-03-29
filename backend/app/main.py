import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.detect import router

app = FastAPI(
    title="CropAI API",
    description="Real-time crop disease detection using YOLO + ResNet18 + Grad-CAM",
    version="1.0.0"
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Read comma-separated origins from env var, e.g.:
#   ALLOWED_ORIGINS=https://cropai.vercel.app,https://crop-ai-app.vercel.app
# Falls back to wildcard if not set (dev mode).
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")

if _raw_origins.strip() == "*":
    allow_origins     = ["*"]
    allow_credentials = False          # credentials=True is incompatible with "*"
else:
    allow_origins     = [o.strip().rstrip("/") for o in _raw_origins.split(",") if o.strip()]
    allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins     = allow_origins,
    allow_credentials = allow_credentials,
    allow_methods     = ["GET", "POST", "OPTIONS"],
    allow_headers     = ["*"],
    expose_headers    = ["*"],
    max_age           = 600,           # cache preflight for 10 min
)

app.include_router(router, prefix="/api")


@app.get("/")
async def root():
    return {
        "status":  "CropAI API running 🌱",
        "docs":    "/docs",
        "origins": allow_origins,
    }


@app.get("/health")
async def health():
    """Lightweight ping endpoint — used by UptimeRobot to prevent cold starts."""
    return {"ok": True}