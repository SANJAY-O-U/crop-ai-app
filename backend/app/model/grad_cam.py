import torch
import numpy as np
import cv2
from PIL import Image

class GradCAM:
    def __init__(self, model, target_layer):
        self.model = model
        self.gradients = None
        self.activations = None

        target_layer.register_forward_hook(self._forward_hook)
        target_layer.register_backward_hook(self._backward_hook)

    def _forward_hook(self, module, input, output):
        self.activations = output.detach()

    def _backward_hook(self, module, grad_input, grad_output):
        self.gradients = grad_output[0].detach()

    def generate(self, input_tensor, class_idx):
        self.model.zero_grad()
        output = self.model(input_tensor)

        score = output[:, class_idx]
        score.backward()

        weights = self.gradients.mean(dim=(2, 3), keepdim=True)
        cam = (weights * self.activations).sum(dim=1).squeeze()

        cam = torch.relu(cam)
        cam = cam.cpu().numpy()

        cam -= cam.min()
        cam /= (cam.max() + 1e-8)

        return cam


def overlay_cam(image: Image.Image, cam, leaf_mask):
    # Resize CAM to image size
    cam = cv2.resize(cam, image.size)

    # Resize leaf mask to image size
    mask_resized = cv2.resize(
        leaf_mask,
        image.size,
        interpolation=cv2.INTER_NEAREST
    )

    # 🔥 APPLY MASK (THIS IS YOUR LINE)
    cam = cam * mask_resized

    # Normalize again after masking
    cam -= cam.min()
    cam /= (cam.max() + 1e-8)

    # Optional threshold for sharpness
    cam = np.where(cam > 0.4, cam, 0)

    heatmap = cv2.applyColorMap(
        np.uint8(255 * cam),
        cv2.COLORMAP_JET
    )

    img = np.array(image)
    overlay = cv2.addWeighted(img, 0.7, heatmap, 0.3, 0)

    return Image.fromarray(overlay)

