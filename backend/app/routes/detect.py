from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from PIL import Image
from app.model.predict import predict_image, CROP_CONFIG

router = APIRouter()


@router.post("/detect")
async def detect(
    crop: str = Form(...),
    file: UploadFile = File(...)
):
    # Validate file type
    if file.content_type not in ["image/jpeg", "image/png", "image/webp", "image/jpg"]:
        raise HTTPException(status_code=400, detail="Only JPEG/PNG/WebP images are supported.")

    try:
        image = Image.open(file.file).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read image file. Please try again.")

    result = predict_image(image, crop.lower())
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