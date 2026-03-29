"""
train_model.py — CropAI Model Training Script
===============================================
Trains a ResNet18 classifier for each crop.

Crops supported:
  tomato · potato · pepper · banana · cotton
  mango  · onion  · rice   · sugarcane · wheat

Usage:
  python train_model.py tomato        # train one crop
  python train_model.py banana        # train a new crop
  python train_model.py all           # train all crops sequentially

Dataset structure (inside backend/ folder):
  dataset_<crop>/
      <ClassName>/
          img1.jpg
          img2.jpg
          ...

Example for banana:
  dataset_banana/
      Healthy/
      Cordana Leaf Spot/
      Panama Wilt/
      Sigatoka/
      Banana Mosaic/

IMPORTANT: Folder names become your class labels.
           They must match the 'classes' list in CROP_CONFIG exactly.
"""

import os
import sys
import json
import time

import torch
from torch import nn, optim
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader, random_split, Subset
from torchvision import datasets, transforms, models
IS_COLAB = "COLAB_GPU" in os.environ

if IS_COLAB:
    BASE_DIR = "/content"
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# ─── CROP CONFIG ──────────────────────────────────────────────────────────────
CROP_CONFIG = {
    # ── Original 3 ──────────────────────────────────────────────────────────
    "tomato": {
        "dataset":    "dataset",
        "classes":    ["healthy", "leaf_blight", "mildew", "rust", "spot"],
        "model_path": "app/model/tomato_model.pth",
        "epochs":     15,
    },
    "potato": {
        "dataset":    "dataset_potato",
        "classes":    ["healthy", "early_blight", "late_blight"],
        "model_path": "app/model/potato_model.pth",
        "epochs":     15,
    },
    "pepper": {
        "dataset":    "dataset_pepper",
        "classes":    ["healthy", "bacterial_spot"],
        "model_path": "app/model/pepper_model.pth",
        "epochs":     12,
    },

    # ── New 7 ────────────────────────────────────────────────────────────────
    "banana": {
        "dataset":    "dataset_banana",
        "classes":    ["Healthy","Panama_Disease"
                       "Sigatoka"],
        "model_path": "app/model/banana_model.pth",
        "epochs":     15,
    },
    "cotton": {
        "dataset":    "dataset_cotton",
        "classes":    ["Healthy", "Bacterial_Blight", "Leaf_Curl",
                       ],
        "model_path": "app/model/cotton_model.pth",
        "epochs":     15,
    },
    "mango": {
        "dataset":    "dataset_mango",
        "classes":    ["Healthy", "Anthracnose", "Powdery_Mildew",
                       ],
        "model_path": "app/model/mango_model.pth",
        "epochs":     15,
    },
    "onion": {
        "dataset":    "dataset_onion",
        "classes":    ["Healthy", "Purple_Blotch",
                       "Downy_Mildew"],
        "model_path": "app/model/onion_model.pth",
        "epochs":     12,
    },
    "rice": {
        "dataset":    "dataset_rice",
        "classes":    ["Healthy","Leaf_smut", "Brown_Spot",
                        "Bacterial_Leaf_Blight"],
        "model_path": "app/model/rice_model.pth",
        "epochs":     15,
    },
    "sugarcane": {
        "dataset":    "dataset_sugarcane",
        "classes":    ["Healthy", "Red_Rot", "Rust",
                       "Mosaic"],
        "model_path": "app/model/sugarcane_model.pth",
        "epochs":     15,
    },
}

# ─── TRANSFORMS ───────────────────────────────────────────────────────────────
TRAIN_TRANSFORM = transforms.Compose([
    transforms.Resize((256, 256)),
    transforms.RandomCrop(224),
    transforms.RandomHorizontalFlip(p=0.5),
    transforms.RandomVerticalFlip(p=0.2),
    transforms.RandomRotation(30),
    transforms.ColorJitter(brightness=0.3, contrast=0.3,
                           saturation=0.25, hue=0.05),
    transforms.RandomGrayscale(p=0.05),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406],
                         [0.229, 0.224, 0.225]),
])

VAL_TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406],
                         [0.229, 0.224, 0.225]),
])


# ─── HELPERS ──────────────────────────────────────────────────────────────────
def build_model(num_classes: int) -> nn.Module:
    """ResNet18 with ImageNet weights, last FC replaced."""
    model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
    model.fc = nn.Linear(model.fc.in_features, num_classes)
    return model


def get_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


class ValSubset(torch.utils.data.Dataset):
    """Wraps a Subset and applies a separate transform for validation."""
    def __init__(self, subset: Subset, transform):
        self.subset    = subset
        self.transform = transform
        # Access the underlying ImageFolder
        self.dataset   = subset.dataset

    def __len__(self):
        return len(self.subset)

    def __getitem__(self, idx):
        real_idx = self.subset.indices[idx]
        path, label = self.dataset.samples[real_idx]
        from PIL import Image as PILImage
        img = PILImage.open(path).convert("RGB")
        return self.transform(img), label


# ─── TRAINING FUNCTION ────────────────────────────────────────────────────────
def train_one_crop(crop_name: str) -> None:
    if crop_name not in CROP_CONFIG:
        print(f"\n❌  Unknown crop: '{crop_name}'")
        print(f"   Available: {', '.join(sorted(CROP_CONFIG.keys()))}")
        return

    cfg         = CROP_CONFIG[crop_name]
    dataset_dir = os.path.join(BASE_DIR, cfg["dataset"])

    if not os.path.isdir(dataset_dir):
        print(f"\n❌  Dataset folder not found: '{dataset_dir}'")
        print(f"   Expected path (relative to backend/): {dataset_dir}/")
        return

    print(f"\n{'='*62}")
    print(f"  Crop        : {crop_name.upper()}")
    print(f"  Dataset     : {dataset_dir}")
    print(f"  Classes     : {cfg['classes']}")
    print(f"  Output      : {cfg['model_path']}")
    print(f"  Epochs      : {cfg['epochs']}")
    print(f"{'='*62}\n")

    # ── Load dataset ──────────────────────────────────────────────────────────
    full_dataset = datasets.ImageFolder(dataset_dir, transform=TRAIN_TRANSFORM)

    # Validate class names
    folder_classes = full_dataset.classes
    config_classes = cfg["classes"]
    missing = set(config_classes) - set(folder_classes)
    extra   = set(folder_classes) - set(config_classes)

    if missing:
        print(f"⚠️  Config classes NOT in folder: {missing}")
    if extra:
        print(f"⚠️  Extra folders not in config (will still be trained): {extra}")
    if not missing and not extra:
        print(f"✅  All {len(folder_classes)} class folders verified.\n")

    n_total = len(full_dataset)
    if n_total == 0:
        print(f"❌  No images found in {dataset_dir}")
        return

    # 80 / 20 split
    n_val   = max(1, int(0.2 * n_total))
    n_train = n_total - n_val
    train_subset, val_subset = random_split(
        full_dataset, [n_train, n_val],
        generator=torch.Generator().manual_seed(42)
    )

    train_loader = DataLoader(
        train_subset, batch_size=32, shuffle=True,
        num_workers=min(4, os.cpu_count() or 1), pin_memory=True
    )
    val_loader = DataLoader(
        ValSubset(val_subset, VAL_TRANSFORM),
        batch_size=32, shuffle=False,
        num_workers=min(4, os.cpu_count() or 1), pin_memory=True
    )

    print(f"  Images total : {n_total}")
    print(f"  Train / Val  : {n_train} / {n_val}")

    # ── Build model ───────────────────────────────────────────────────────────
    num_classes = len(full_dataset.classes)
    model       = build_model(num_classes)
    device      = get_device()
    print(f"  Classes      : {num_classes}")
    print(f"  Device       : {device}\n")
    model.to(device)

    # ── Optimizer + scheduler ─────────────────────────────────────────────────
    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)
    optimizer = optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-4)
    scheduler = CosineAnnealingLR(optimizer,
                                  T_max=cfg["epochs"], eta_min=1e-6)

    best_val_acc = 0.0
    best_state   = None
    history      = []

    # ── Epoch loop ────────────────────────────────────────────────────────────
    for epoch in range(1, cfg["epochs"] + 1):
        t0 = time.time()

        # — Train —
        model.train()
        tr_loss, tr_ok, tr_n = 0.0, 0, 0
        for imgs, labels in train_loader:
            imgs, labels = imgs.to(device), labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            out  = model(imgs)
            loss = criterion(out, labels)
            loss.backward()
            optimizer.step()
            tr_loss += loss.item() * imgs.size(0)
            tr_ok   += (out.argmax(1) == labels).sum().item()
            tr_n    += imgs.size(0)

        scheduler.step()

        # — Validate —
        model.eval()
        va_loss, va_ok, va_n = 0.0, 0, 0
        with torch.no_grad():
            for imgs, labels in val_loader:
                imgs, labels = imgs.to(device), labels.to(device)
                out  = model(imgs)
                loss = criterion(out, labels)
                va_loss += loss.item() * imgs.size(0)
                va_ok   += (out.argmax(1) == labels).sum().item()
                va_n    += imgs.size(0)

        t_acc = tr_ok / tr_n * 100
        v_acc = va_ok / va_n * 100
        t_l   = tr_loss / tr_n
        v_l   = va_loss / va_n
        dt    = time.time() - t0

        is_best = v_acc > best_val_acc
        marker  = "  ✅ BEST" if is_best else ""

        print(f"  Epoch [{epoch:02d}/{cfg['epochs']:02d}]  "
              f"Train {t_acc:5.1f}% (loss {t_l:.4f})  |  "
              f"Val {v_acc:5.1f}% (loss {v_l:.4f})  "
              f"[{dt:.1f}s]{marker}")

        history.append({
            "epoch": epoch,
            "train_loss": round(t_l, 4), "train_acc": round(t_acc, 2),
            "val_loss":   round(v_l, 4), "val_acc":   round(v_acc, 2),
        })

        if is_best:
            best_val_acc = v_acc
            best_state   = {k: v.cpu().clone()
                            for k, v in model.state_dict().items()}

    # ── Save best model ────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(cfg["model_path"]) or ".", exist_ok=True)
    model_path = os.path.join(BASE_DIR, cfg["model_path"])
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    torch.save(best_state, model_path)

    meta = {
        "crop":          crop_name,
        "folder_classes": folder_classes,
        "config_classes": config_classes,
        "num_classes":   num_classes,
        "best_val_acc":  round(best_val_acc, 2),
        "history":       history,
    }
    meta_path = cfg["model_path"].replace(".pth", "_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\n✅  Saved  →  {cfg['model_path']}")
    print(f"   Metadata   →  {meta_path}")
    print(f"   Best Val   →  {best_val_acc:.2f}%\n")


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        print(f"Available crops: {', '.join(sorted(CROP_CONFIG.keys()))}")
        sys.exit(1)

    target = sys.argv[1].lower().strip()

    if target == "all":
        print("🌾  Training ALL 10 crops sequentially...\n")
        failed = []
        for crop in CROP_CONFIG:
            try:
                train_one_crop(crop)
            except Exception as exc:
                print(f"❌  {crop} failed: {exc}\n")
                failed.append(crop)
        print("─" * 62)
        if failed:
            print(f"⚠️  Failed: {failed}")
        else:
            print("🎉  All crops trained successfully!")
    else:
        train_one_crop(target)