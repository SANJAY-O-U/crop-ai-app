from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.detect import router

app = FastAPI(
    title="CropAI API",
    description="Real-time crop disease detection using YOLO + ResNet18 + Grad-CAM",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
async def root():
    return {"status": "CropAI API running 🌱", "docs": "/docs"}