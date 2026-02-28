import torch
import torch.nn.functional as F
import base64
import io

from torchvision import transforms
from PIL import Image
from .model import load_model
from app.model.leaf_detector import detect_leaf
from app.model.grad_cam import GradCAM, overlay_cam

CONFIDENCE_THRESHOLD = 0.60

CROP_CONFIG = {
    "tomato": {
        "model_path": "app/model/crop_model.pth",
        "classes": ["Healthy", "Leaf Blight", "Mildew", "Rust", "Spot"]
    },
    "potato": {
        "model_path": "app/model/potato_model.pth",
        "classes": ["Healthy", "Early Blight", "Late Blight"]
    },
    "pepper": {
        "model_path": "app/model/pepper_model.pth",
        "classes": ["Healthy", "Bacterial Spot"]
    }
}

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor()
])

_loaded_models = {}

def load_crop_model(crop):
    if crop not in _loaded_models:
        config = CROP_CONFIG[crop]
        model = load_model(len(config["classes"]))
        model.load_state_dict(
            torch.load(config["model_path"], map_location="cpu")
        )
        model.eval()
        _loaded_models[crop] = model
    return _loaded_models[crop]
def encode_image(img):
    if img is None:
        return None
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode()

def predict_image(image: Image.Image, crop: str):
    if crop not in CROP_CONFIG:
        return {"status": "error", "message": "Unsupported crop"}

    model = load_crop_model(crop)
    classes = CROP_CONFIG[crop]["classes"]

    leaf_img, boxed_img, leaf_mask = detect_leaf(image)
    img = transform(leaf_img).unsqueeze(0)


    with torch.no_grad():
        outputs = model(img)
        probs = F.softmax(outputs, dim=1)[0]

    # Top-3 predictions
    topk = torch.topk(probs, k=min(3, len(classes)))

    predictions = []
    for idx, score in zip(topk.indices, topk.values):
        predictions.append({
            "label": classes[idx],
            "confidence": round(score.item() * 100, 2)
        })

    best = predictions[0] 
    # -------- GRAD-CAM --------
    target_layer = model.layer3[-1]  # 🔥 much better localization
  # ResNet18 last conv block
    cam_generator = GradCAM(model, target_layer)

    cam = cam_generator.generate(img, idx.item())
    cam_overlay = overlay_cam(leaf_img, cam, leaf_mask)

    
    # Healthy guard
    if best["label"].lower() == "healthy" and best["confidence"] > 90:
        return {
            "status": "warning",
            "crop": crop.capitalize(),
            "message": "Model may be overconfident. Please retake image.",
            "top_predictions": predictions
        }

    # Confidence rejection
    if best["confidence"] < CONFIDENCE_THRESHOLD * 100:
        return {
            "status": "rejected",
            "message": f"Not a valid {crop} leaf",
            "top_predictions": predictions
        }

    return {
    "status": "success",
    "crop": crop.capitalize(),
    "disease": best["label"],
    "confidence": best["confidence"],
    "top_predictions": predictions,
    "boxed_image": encode_image(boxed_img),
    "grad_cam": encode_image(cam_overlay)

}

    return {
    "status": "warning",
    "crop": crop.capitalize(),
    "message": "Model may be overconfident. Please retake image.",
    "top_predictions": predictions,
    "boxed_image": encode_image(boxed_img)
}


