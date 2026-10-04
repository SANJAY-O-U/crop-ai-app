"""
Disease-detection model artifacts: inventory, location and readiness. Deliberately LIGHT (no torch / ultralytics import)
so it can run before the heavy model modules are imported and in tests.

Source of truth for what must exist: backend/model_manifest.json (file names, sizes, SHA-256 — no URLs, no secrets).
A test asserts the manifest agrees with CROP_CONFIG in predict.py.

Location: files live in MODEL_DIR (env; default `backend/app/model`, resolved from this file — NOT from the process
working directory). `yolov8n.pt` (the leaf detector) lives one level up, in `backend/`, unless MODEL_DIR is set, in which
case it is looked up there as well.

Environment:
  MODEL_DIR               directory holding the 9 `*_model.pth` files (and optionally yolov8n.pt)
  MODEL_MANIFEST          path of an alternative manifest (tests / staging)
  REQUIRE_DISEASE_MODELS  true -> the process REFUSES TO START if any required model file is missing or has the wrong
                          size (recommended in production: the deploy then fails instead of serving a broken detector)
"""

import json
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = BACKEND_DIR / "model_manifest.json"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def strict_startup() -> bool:
    return _truthy(os.getenv("REQUIRE_DISEASE_MODELS"))


def model_dir() -> Path:
    raw = os.getenv("MODEL_DIR", "").strip()
    return Path(raw).expanduser().resolve() if raw else DEFAULT_MODEL_DIR


def load_manifest() -> dict:
    path = Path(os.getenv("MODEL_MANIFEST", "").strip() or DEFAULT_MANIFEST)
    return json.loads(path.read_text(encoding="utf-8"))


def resolve(model_path: str | os.PathLike) -> Path:
    """Map a CROP_CONFIG path such as 'app/model/tomato_model.pth' to the real file: the file name is looked up in
    MODEL_DIR, independent of the working directory. Absolute paths are honoured as given."""
    p = Path(model_path)
    return p if p.is_absolute() else model_dir() / p.name


def _file_state(path: Path, expected_size: int | None) -> str:
    if not path.is_file():
        return "missing"
    if expected_size is not None and path.stat().st_size != expected_size:
        return "wrong_size"
    return "ok"


def status() -> dict:
    """Cheap (stat only, no hashing, no file contents) readiness of the disease-detection artifacts."""
    manifest = load_manifest()
    base = model_dir()
    models = manifest["disease_models"]
    states = {crop: _file_state(base / m["file"], m.get("size_bytes")) for crop, m in models.items()}
    missing = sorted(models[c]["file"] for c, s in states.items() if s == "missing")
    wrong = sorted(models[c]["file"] for c, s in states.items() if s == "wrong_size")
    yolo = manifest.get("leaf_detector")
    yolo_state = "n/a"
    if yolo:
        yolo_state = "ok" if any(_file_state(d / yolo["file"], yolo.get("size_bytes")) == "ok" for d in (base, BACKEND_DIR)) else "missing"
    ok_models = [c for c, s in states.items() if s == "ok"]
    return {
        "ready": not missing and not wrong and yolo_state in ("ok", "n/a"),
        "present": len(ok_models),
        "expected": len(models),
        "missing": missing,
        "wrong_size": wrong,
        "available_crops": sorted(ok_models),
        "leaf_detector": {"file": yolo["file"] if yolo else None, "present": yolo_state == "ok"},
        "model_dir_is_default": not os.getenv("MODEL_DIR", "").strip(),
        "strict_startup": strict_startup(),
    }


def crop_available(crop: str) -> bool:
    manifest = load_manifest()
    entry = manifest["disease_models"].get(crop.lower().strip())
    return bool(entry) and _file_state(model_dir() / entry["file"], entry.get("size_bytes")) == "ok"


class DiseaseModelsMissingError(RuntimeError):
    pass


def enforce_startup() -> dict:
    """Fail fast (clearly) when REQUIRE_DISEASE_MODELS is set and artifacts are absent; otherwise just report."""
    st = status()
    if strict_startup() and not st["ready"]:
        problems = []
        if st["missing"]:
            problems.append("missing: " + ", ".join(st["missing"]))
        if st["wrong_size"]:
            problems.append("wrong size: " + ", ".join(st["wrong_size"]))
        if not st["leaf_detector"]["present"]:
            problems.append(f"leaf detector {st['leaf_detector']['file']} not found")
        raise DiseaseModelsMissingError(
            f"REQUIRE_DISEASE_MODELS is set but the disease-detection artifacts are incomplete ({st['present']}/{st['expected']} models). "
            + "; ".join(problems) + ". Install them with `python scripts/fetch_models.py` (see docs/PRODUCTION_DEPLOYMENT.md)."
        )
    return st
