import torch
import numpy as np
import cv2
from PIL import Image


class GradCAM:
    def __init__(self, model, target_layer):
        self.model = model
        self.gradients = None
        self.activations = None

        target_layer.register_forward_hook(self.forward_hook)
        target_layer.register_full_backward_hook(self.backward_hook)

    def forward_hook(self, module, input, output):
        self.activations = output.detach()

    def backward_hook(self, module, grad_input, grad_output):
        self.gradients = grad_output[0].detach()

    def generate(self, input_tensor, class_idx):

        self.model.zero_grad()

        output = self.model(input_tensor)

        score = output[:, class_idx]

        score.backward()

        gradients = self.gradients
        activations = self.activations

        # Global average pooling
        weights = torch.mean(gradients, dim=(2, 3), keepdim=True)

        cam = torch.sum(weights * activations, dim=1)

        cam = torch.relu(cam)

        cam = cam.squeeze().cpu().numpy()

        # Normalize CAM
        cam -= cam.min()
        cam /= (cam.max() + 1e-8)

        # Smooth CAM
        cam = cv2.GaussianBlur(cam, (7, 7), 0)

        return cam


def overlay_cam(image: Image.Image, cam, leaf_mask):

    img = np.array(image)

    cam = cv2.resize(cam, (img.shape[1], img.shape[0]))

    # Restrict CAM to detected leaf region
    if leaf_mask is not None:
        mask = cv2.resize(leaf_mask, (img.shape[1], img.shape[0]))
        cam = cam * mask

    # Remove weak activations (noise suppression)
    cam = np.where(cam > 0.35, cam, 0)

    cam -= cam.min()
    cam /= (cam.max() + 1e-8)

    heatmap = cv2.applyColorMap(
        np.uint8(255 * cam),
        cv2.COLORMAP_TURBO
    )

    overlay = cv2.addWeighted(img, 0.75, heatmap, 0.35, 0)

    return Image.fromarray(overlay)