import torch
import torchvision.models as models
import torch.nn as nn

def load_model(num_classes=5):
    model = models.resnet18(pretrained=True)
    model.fc = nn.Linear(model.fc.in_features, num_classes)
    return model
