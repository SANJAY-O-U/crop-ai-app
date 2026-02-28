from fastapi import APIRouter, File, UploadFile, Form
from PIL import Image
from app.model.predict import predict_image


router = APIRouter()

@router.post("/detect")
async def detect(
    crop: str = Form(...),
    file: UploadFile = File(...)
):
    image = Image.open(file.file).convert("RGB")
    result = predict_image(image, crop.lower())
    return result

