import torch
import torch.nn.functional as F
import base64
import io
import numpy as np
import cv2

from torchvision import transforms
from PIL import Image
from .model import load_model
from app.model.leaf_detector import detect_leaf
from app.model.grad_cam import GradCAM, overlay_cam

CONFIDENCE_THRESHOLD = 0.60

# ─── CROP CONFIG — 10 crops ───────────────────────────────────────────────────
# classes must match training folder names EXACTLY (case-sensitive)
CROP_CONFIG = {
    # ── Original 3 ──────────────────────────────────────────────────────────
    "tomato": {

        "classes":    ["healthy", "leaf_blight", "mildew", "rust", "spot"],
        "model_path": "app/model/tomato_model.pth",

    },
    "potato": {
  
        "classes":    ["healthy", "early_blight", "late_blight"],
        "model_path": "app/model/potato_model.pth",

    },
    "pepper": {

        "classes":    ["healthy", "bacterial_spot"],
        "model_path": "app/model/pepper_model.pth",

    },

    # ── New 7 ────────────────────────────────────────────────────────────────
    "banana": {

        "classes":    ["Healthy","Panama_Disease",
                       "Sigatoka"],
        "model_path": "app/model/banana_model.pth",
  
    },
    "cotton": {

        "classes":    ["Healthy", "Bacterial_Blight", "Leaf_Curl",
                       ],
        "model_path": "app/model/cotton_model.pth",
  
    },
    "mango": {

        "classes":    ["Healthy", "Anthracnose", "Powdery_Mildew",
                       ],
        "model_path": "app/model/mango_model.pth",

    },
    "onion": {

        "classes":    ["Healthy", "Purple_Blotch",
                       "Downy_Mildew"],
        "model_path": "app/model/onion_model.pth",

    },
    "rice": {

        "classes":    ["Healthy","Leaf_smut", "Brown_Spot",
                        "Bacterial_Leaf_Blight"],
        "model_path": "app/model/rice_model.pth",

    },
    "sugarcane": {

        "classes":    ["Healthy", "Red_Rot", "Rust",
                       "Mosaic"],
        "model_path": "app/model/sugarcane_model.pth",
    },
}

# Normalisation must match training pipeline
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406],
                         [0.229, 0.224, 0.225]),
])

_loaded_models = {}


def load_crop_model(crop):
    if crop not in _loaded_models:
        config = CROP_CONFIG[crop]
        model  = load_model(len(config["classes"]))
        model.load_state_dict(
            torch.load(config["model_path"], map_location="cpu")
        )
        model.eval()
        _loaded_models[crop] = model
    return _loaded_models[crop]


def encode_image(img):
    if img is None:
        return None
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def is_leaf_image(image: Image.Image):
    """
    Green-ratio pre-filter. Widened hue range covers yellowing/dry leaves
    common in wheat, onion, sugarcane crops.
    """
    img = np.array(image)
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    lower_green = np.array([18, 30, 30])
    upper_green = np.array([95, 255, 255])
    mask = cv2.inRange(hsv, lower_green, upper_green)
    green_ratio = np.sum(mask > 0) / mask.size
    return green_ratio > 0.04


def predict_image(image: Image.Image, crop: str):
    crop = crop.lower().strip()

    if crop not in CROP_CONFIG:
        supported = ", ".join(sorted(CROP_CONFIG.keys()))
        return {
            "status":  "error",
            "message": f"Unsupported crop '{crop}'. Supported: {supported}"
        }

    # Step 1: Leaf validation
    if not is_leaf_image(image):
        return {
            "status":  "rejected",
            "message": "No leaf detected. Please upload a clear leaf image."
        }

    model   = load_crop_model(crop)
    classes = CROP_CONFIG[crop]["classes"]

    # Step 2: YOLO leaf detection (fallback to full image if YOLO misses)
    leaf_img, boxed_img, leaf_mask = detect_leaf(image)
    if leaf_img is None:
        leaf_img, boxed_img, leaf_mask = image, image, None

    img_tensor = transform(leaf_img).unsqueeze(0)

    # Step 3: ResNet18 classification
    with torch.no_grad():
        outputs = model(img_tensor)
        probs   = F.softmax(outputs, dim=1)[0]

    topk = torch.topk(probs, k=min(3, len(classes)))

    predictions = []
    for idx, score in zip(topk.indices, topk.values):
        # Normalise class name: replace underscores with spaces so frontend
        # DISEASE_INFO lookup always works ("Leaf_Curl" → "Leaf Curl")
        raw_label   = classes[idx.item()]
        clean_label = raw_label.replace("_", " ").strip()
        predictions.append({
            "label":      clean_label,
            "confidence": round(score.item() * 100, 2)
        })

    best = predictions[0]

    # Step 4: Grad-CAM
    target_layer  = model.layer3[-1]
    cam_generator = GradCAM(model, target_layer)
    cam           = cam_generator.generate(img_tensor, topk.indices[0].item())
    cam_overlay   = overlay_cam(leaf_img, cam, leaf_mask)

    # Step 5: Healthy guard
    if best["label"].lower() == "healthy" and best["confidence"] > 88:
        return {
            "status":          "success",
            "crop":            crop.capitalize(),
            "disease":         "Healthy",
            "confidence":      best["confidence"],
            "top_predictions": predictions,
            "boxed_image":     encode_image(boxed_img),
            "grad_cam":        encode_image(cam_overlay),
            "is_healthy":      True,
        }

    # Step 6: Confidence gate
    if best["confidence"] < CONFIDENCE_THRESHOLD * 100:
        return {
            "status":          "rejected",
            "message":         f"Low confidence ({best['confidence']:.1f}%). "
                               f"Please upload a clearer {crop} leaf image.",
            "top_predictions": predictions,
        }

    return {
        "status":          "success",
        "crop":            crop.capitalize(),
        "disease":         best["label"],
        "confidence":      best["confidence"],
        "top_predictions": predictions,
        "boxed_image":     encode_image(boxed_img),
        "grad_cam":        encode_image(cam_overlay),
        "is_healthy":      False,
    }