import os

from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from PIL import Image
from app.api_errors import APIError
from app.model import artifacts
from app.model.predict import predict_image, CROP_CONFIG

router = APIRouter()

MAX_UPLOAD_BYTES = int(float(os.getenv("MAX_UPLOAD_MB", "15")) * 1024 * 1024)   # reject oversized uploads early


@router.post("/detect")
async def detect(
    crop: str = Form(...),
    file: UploadFile = File(...)
):
    # Validate file type
    if file.content_type not in ["image/jpeg", "image/png", "image/webp", "image/jpg"]:
        raise HTTPException(status_code=400, detail="Only JPEG/PNG/WebP images are supported.")

    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image is too large. Please upload a smaller photo.")

    try:
        image = Image.open(file.file).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read image file. Please try again.")

    crop_key = crop.lower().strip()
    if crop_key in CROP_CONFIG and not artifacts.crop_available(crop_key):
        # A supported crop whose model file is absent/corrupt: say so plainly instead of a 500 from torch.load.
        raise APIError(503, "disease_models_unavailable", "Disease detection for this crop is temporarily unavailable. Please try again later.",
                       headers={"Retry-After": "300"})

    result = predict_image(image, crop_key)
    return result


@router.get("/crops")
async def get_crops():
    """Return list of supported crops with their disease classes."""
    return {
        crop: {
            "name": crop.capitalize(),
            "classes": config["classes"],
            "disease_count": len([c for c in config["classes"] if c.lower() != "healthy"])
        }
        for crop, config in CROP_CONFIG.items()
    }


@router.get("/health")
async def health():
    return {"status": "ok", "message": "CropAI API is running 🌱"}