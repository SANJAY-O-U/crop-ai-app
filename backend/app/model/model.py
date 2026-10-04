import torch
import torchvision.models as models
import torch.nn as nn

def load_model(num_classes=5):
    # weights=None: every caller immediately loads a full fine-tuned state_dict over this network, so the ImageNet
    # initialisation is never used (outputs verified bit-identical) and no download is needed at runtime.
    model = models.resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, num_classes)
    return model
