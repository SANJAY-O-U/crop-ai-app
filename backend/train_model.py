import os
import sys
import torch
from torchvision import datasets, transforms
from torch import nn, optim
from app.model.model import load_model

# ---------- CONFIG ----------
CROP = sys.argv[1]  # tomato / potato / pepper

CONFIG = {
    "tomato": {
        "dataset": "dataset_tomato",
        "classes": ["healthy", "leaf_blight", "mildew", "rust", "spot"],
        "model_path": "app/model/tomato_model.pth"
    },
    "potato": {
        "dataset": "dataset_potato",
        "classes": ["healthy", "early_blight", "late_blight"],
        "model_path": "app/model/potato_model.pth"
    },
    "pepper": {
        "dataset": "dataset_pepper",
        "classes": ["healthy", "bacterial_spot"],
        "model_path": "app/model/pepper_model.pth"
    }
}

if CROP not in CONFIG:
    raise Exception("❌ Unknown crop")

config = CONFIG[CROP]

# ---------- TRANSFORMS ----------
train_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.RandomHorizontalFlip(p=0.5),
    transforms.RandomRotation(20),
    transforms.ColorJitter(
        brightness=0.3,
        contrast=0.3,
        saturation=0.2,
        hue=0.02
    ),
    transforms.ToTensor()
])


dataset = datasets.ImageFolder(
    config["dataset"],
    transform=train_transform
)


print("✅ Crop:", CROP)
print("✅ Classes:", dataset.classes)
print("✅ Total images:", len(dataset))

if len(dataset) == 0:
    raise Exception("❌ Dataset is empty")

loader = torch.utils.data.DataLoader(dataset, batch_size=16, shuffle=True)

model = load_model(len(dataset.classes))
criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(model.parameters(), lr=0.001)

# ---------- TRAIN ----------
epochs = 12
for epoch in range(epochs):
    running_loss = 0.0
    for images, labels in loader:
        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()
        running_loss += loss.item()

    print(f"Epoch [{epoch+1}/{epochs}] Loss: {running_loss:.4f}")

# ---------- SAVE ----------
os.makedirs("app/model", exist_ok=True)
torch.save(model.state_dict(), config["model_path"])

print(f"✅ {CROP.capitalize()} model trained & saved")
