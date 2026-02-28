from ultralytics import YOLO
import numpy as np
from PIL import Image, ImageDraw

yolo_model = YOLO("yolov8n.pt")
def detect_leaf(image):
    img = np.array(image)
    results = yolo_model(img)

    if len(results[0].boxes) == 0:
        h, w = img.shape[:2]
        mask = np.ones((h, w), dtype=np.float32)
        return image, image, mask

    boxes = results[0].boxes.xyxy.cpu().numpy()
    areas = [(x2 - x1) * (y2 - y1) for x1, y1, x2, y2 in boxes]
    idx = areas.index(max(areas))

    x1, y1, x2, y2 = map(int, boxes[idx])

    cropped = img[y1:y2, x1:x2]
    cropped_pil = Image.fromarray(cropped)

    vis_img = image.copy()
    draw = ImageDraw.Draw(vis_img)
    draw.rectangle([x1, y1, x2, y2], outline="red", width=3)

    mask = np.zeros(img.shape[:2], dtype=np.float32)
    mask[y1:y2, x1:x2] = 1.0

    return cropped_pil, vis_img, mask




