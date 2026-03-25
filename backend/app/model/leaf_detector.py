from ultralytics import YOLO
import numpy as np
from PIL import Image, ImageDraw
import cv2

# Load YOLO model
yolo_model = YOLO("yolov8n.pt")


def detect_leaf(image):
    img = np.array(image)

    # Optional: green color filtering to remove background noise
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower_green = np.array([25, 40, 40])
    upper_green = np.array([85, 255, 255])
    mask_green = cv2.inRange(hsv, lower_green, upper_green)
    img_filtered = cv2.bitwise_and(img, img, mask=mask_green)

    # Run YOLO detection (lower confidence improves stability)
    results = yolo_model(img_filtered, conf=0.25)

    # If no leaf detected → fallback to full image
    if results[0].boxes is None or len(results[0].boxes) == 0:
        h, w = img.shape[:2]
        mask = np.ones((h, w), dtype=np.float32)
        return image, image, mask

    # Extract bounding boxes
    boxes = results[0].boxes.xyxy.cpu().numpy()

    # Select largest box (most likely the main leaf)
    largest_box = None
    largest_area = 0

    for box in boxes:
        x1, y1, x2, y2 = map(int, box)
        area = (x2 - x1) * (y2 - y1)

        if area > largest_area:
            largest_area = area
            largest_box = (x1, y1, x2, y2)

    x1, y1, x2, y2 = largest_box

    # Add padding to stabilize detection
    padding = 20
    x1 = max(0, x1 - padding)
    y1 = max(0, y1 - padding)
    x2 = min(img.shape[1], x2 + padding)
    y2 = min(img.shape[0], y2 + padding)

    # Crop leaf region
    cropped = img[y1:y2, x1:x2]
    cropped_pil = Image.fromarray(cropped)

    # Draw YOLO bounding box
    vis_img = image.copy()
    draw = ImageDraw.Draw(vis_img)
    draw.rectangle([x1, y1, x2, y2], outline="red", width=3)

    # Create mask for GradCAM restriction
    mask = np.zeros(img.shape[:2], dtype=np.float32)
    mask[y1:y2, x1:x2] = 1.0

    return cropped_pil, vis_img, mask




