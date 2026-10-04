"""Disease-model artifacts: inventory, readiness semantics, startup validation, safe loading, installer, environment checks.
Uses small fake files and temporary directories; the real 384 MB of weights are never required (one test skips if absent)."""

import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import torch
import torchvision.models as tv_models
from fastapi.testclient import TestClient
from PIL import Image

from app import config_check
from app.model import artifacts
from app.model import predict as predict_module
from app.model.predict import CROP_CONFIG

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "fetch_models.py"


def load_script():
    spec = importlib.util.spec_from_file_location("fetch_models_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_manifest(tmp_path, crops=("tomato", "potato"), payload=b"model-bytes", yolo=True):
    manifest = {"manifest_version": 1, "disease_models": {}}
    for c in crops:
        manifest["disease_models"][c] = {"file": f"{c}_model.pth", "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
    if yolo:
        manifest["leaf_detector"] = {"file": "yolov8n.pt", "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A tiny manifest + empty MODEL_DIR; returns helpers."""
    for v in ("REQUIRE_DISEASE_MODELS", "MODEL_ARTIFACT_BASE_URL", "MODEL_ARTIFACT_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    models = tmp_path / "models"
    models.mkdir()
    manifest = make_manifest(tmp_path)
    monkeypatch.setenv("MODEL_DIR", str(models))
    monkeypatch.setenv("MODEL_MANIFEST", str(manifest))
    return type("E", (), {"dir": models, "manifest": manifest, "tmp": tmp_path})


def fill(env, names=("tomato_model.pth", "potato_model.pth", "yolov8n.pt"), payload=b"model-bytes"):
    for n in names:
        (env.dir / n).write_bytes(payload)


# ── inventory ────────────────────────────────────────────────────────────────────────────────────────────
def test_manifest_is_the_exact_inventory_of_crop_config():
    m = json.loads(artifacts.DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    assert set(m["disease_models"]) == set(CROP_CONFIG) and len(m["disease_models"]) == 9
    for crop, entry in m["disease_models"].items():
        assert entry["file"] == Path(CROP_CONFIG[crop]["model_path"]).name == f"{crop}_model.pth"
        assert entry["size_bytes"] > 1_000_000 and re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
    assert m["leaf_detector"]["file"] == "yolov8n.pt" and re.fullmatch(r"[0-9a-f]{64}", m["leaf_detector"]["sha256"])
    assert "http" not in artifacts.DEFAULT_MANIFEST.read_text(encoding="utf-8").lower()        # no URLs / credentials in the manifest


def test_model_paths_are_gitignored_and_untracked():
    root = BACKEND.parent
    for crop in CROP_CONFIG:
        rel = f"backend/app/model/{crop}_model.pth"
        assert subprocess.run(["git", "check-ignore", "-q", rel], cwd=root).returncode == 0
    tracked = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True).stdout.splitlines()
    assert not [f for f in tracked if f.endswith((".pth", ".pt"))]


# ── status / missing detection ───────────────────────────────────────────────────────────────────────────
def test_all_present_is_ready(env):
    fill(env)
    st = artifacts.status()
    assert st["ready"] and st["present"] == st["expected"] == 2 and st["missing"] == [] and st["wrong_size"] == []
    assert st["available_crops"] == ["potato", "tomato"] and st["leaf_detector"]["present"] is True


def test_missing_model_is_named_and_makes_detection_not_ready(env):
    fill(env, names=("tomato_model.pth", "yolov8n.pt"))
    st = artifacts.status()
    assert st["ready"] is False and st["present"] == 1 and st["expected"] == 2 and st["missing"] == ["potato_model.pth"]
    assert artifacts.crop_available("tomato") and not artifacts.crop_available("potato") and not artifacts.crop_available("wheat")


def test_wrong_size_file_is_not_counted_as_present(env):
    fill(env)
    (env.dir / "potato_model.pth").write_bytes(b"truncated")
    st = artifacts.status()
    assert st["ready"] is False and st["wrong_size"] == ["potato_model.pth"] and st["present"] == 1


def test_missing_leaf_detector_blocks_readiness(env):
    fill(env, names=("tomato_model.pth", "potato_model.pth"))
    st = artifacts.status()
    assert st["ready"] is False and st["leaf_detector"]["present"] is False and st["missing"] == []


def test_real_manifest_against_an_empty_directory_reports_nine_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("MODEL_MANIFEST", raising=False)
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    st = artifacts.status()
    assert st["present"] == 0 and st["expected"] == 9 and len(st["missing"]) == 9 and st["ready"] is False


@pytest.mark.skipif(not all((artifacts.DEFAULT_MODEL_DIR / f"{c}_model.pth").exists() for c in CROP_CONFIG), reason="model weights not installed here")
def test_real_artifacts_match_the_manifest_when_installed(monkeypatch):
    monkeypatch.delenv("MODEL_DIR", raising=False)
    monkeypatch.delenv("MODEL_MANIFEST", raising=False)
    st = artifacts.status()
    assert st["ready"] and st["present"] == 9 and st["wrong_size"] == []


# ── startup validation ───────────────────────────────────────────────────────────────────────────────────
def test_strict_startup_raises_with_a_clear_message_naming_the_files(env, monkeypatch):
    monkeypatch.setenv("REQUIRE_DISEASE_MODELS", "true")
    fill(env, names=("tomato_model.pth", "yolov8n.pt"))
    with pytest.raises(artifacts.DiseaseModelsMissingError) as ei:
        artifacts.enforce_startup()
    msg = str(ei.value)
    assert "REQUIRE_DISEASE_MODELS" in msg and "potato_model.pth" in msg and "1/2" in msg and "fetch_models.py" in msg


def test_strict_startup_passes_when_complete_and_non_strict_never_raises(env, monkeypatch):
    assert artifacts.enforce_startup()["ready"] is False                      # not strict: reports, does not raise
    monkeypatch.setenv("REQUIRE_DISEASE_MODELS", "1")
    fill(env)
    assert artifacts.enforce_startup()["ready"] is True


def test_process_refuses_to_start_in_strict_mode_without_models(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = subprocess.run([sys.executable, "-c", "import app.main"], cwd=BACKEND, capture_output=True, text=True, timeout=120,
                          env={**os.environ, "REQUIRE_DISEASE_MODELS": "true", "MODEL_DIR": str(empty), "PYTHONDONTWRITEBYTECODE": "1"})
    assert proc.returncode != 0
    assert "DiseaseModelsMissingError" in proc.stderr and "tomato_model.pth" in proc.stderr and "0/9" in proc.stderr


# ── readiness semantics through the API ──────────────────────────────────────────────────────────────────
def client():
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


def test_ready_separates_application_weather_and_disease_readiness(env):
    body = client().get("/ready").json()
    assert body["ready"] is True and body["readiness"] == {"application": True, "weather": True, "disease_detection": False}
    assert body["status"] == "degraded"
    d = body["disease_detection_models"]
    assert d["present"] == 0 and d["expected"] == 2 and d["missing"] == ["potato_model.pth", "tomato_model.pth"] and d["ready"] is False
    assert d["affects_readiness"] is False                                  # weather keeps working without disease models


def test_ready_reports_ok_when_everything_is_installed(env):
    fill(env)
    r = client().get("/ready")
    b = r.json()
    assert r.status_code == 200 and b["status"] == "ok" and b["readiness"]["disease_detection"] is True
    assert b["disease_detection_models"]["missing"] == [] and "configuration" in b


def test_health_is_unaffected_by_missing_models(env):
    assert client().get("/health").json() == {"ok": True}


def png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (40, 160, 40)).save(buf, format="PNG")
    return buf.getvalue()


def test_detect_returns_a_clear_503_when_the_crop_model_is_absent(env):
    r = client().post("/api/detect", data={"crop": "tomato"}, files={"file": ("leaf.png", png_bytes(), "image/png")})
    assert r.status_code == 503 and r.headers["retry-after"]
    b = r.json()
    assert b["error"]["code"] == "disease_models_unavailable" and isinstance(b["detail"], str) and "Traceback" not in r.text


def test_detect_keeps_legacy_behaviour_for_unsupported_crops(env):
    r = client().post("/api/detect", data={"crop": "wheat"}, files={"file": ("leaf.png", png_bytes(), "image/png")})
    assert r.status_code == 200 and r.json()["status"] == "error"


# ── path handling ────────────────────────────────────────────────────────────────────────────────────────
def test_paths_resolve_from_model_dir_independent_of_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_DIR", str(tmp_path / "m"))
    monkeypatch.chdir(tmp_path)
    assert artifacts.resolve("app/model/tomato_model.pth") == (tmp_path / "m").resolve() / "tomato_model.pth"
    absolute = tmp_path / "elsewhere" / "x.pth"
    assert artifacts.resolve(absolute) == absolute


def test_default_model_dir_is_backend_app_model_not_the_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("MODEL_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert artifacts.model_dir() == (BACKEND / "app" / "model").resolve()
    assert artifacts.resolve("app/model/rice_model.pth") == BACKEND / "app" / "model" / "rice_model.pth"


# ── safe loading ─────────────────────────────────────────────────────────────────────────────────────────
def test_checkpoints_are_loaded_with_weights_only_and_the_resolved_path(env, monkeypatch):
    seen = {}
    n = len(CROP_CONFIG["pepper"]["classes"])
    net = tv_models.resnet18(weights=None)
    net.fc = torch.nn.Linear(net.fc.in_features, n)

    def fake_load(path, **kw):
        seen.update(path=Path(path), **kw)
        return net.state_dict()

    monkeypatch.setattr(predict_module.torch, "load", fake_load)
    monkeypatch.setattr(predict_module, "_loaded_models", {})
    predict_module.load_crop_model("pepper")
    assert seen["weights_only"] is True and seen["map_location"] == "cpu" and seen["path"] == env.dir / "pepper_model.pth"


def test_model_construction_never_downloads_imagenet_weights(monkeypatch):
    calls = {}
    real = tv_models.resnet18
    monkeypatch.setattr("app.model.model.models.resnet18", lambda **kw: (calls.update(kw), real(weights=None))[1])
    from app.model.model import load_model
    load_model(3)
    assert calls == {"weights": None}


# ── installer ────────────────────────────────────────────────────────────────────────────────────────────
def test_installer_downloads_verifies_and_installs_atomically(env, monkeypatch, capsys):
    src = env.tmp / "store"
    src.mkdir()
    for n in ("tomato_model.pth", "potato_model.pth", "yolov8n.pt"):
        (src / n).write_bytes(b"model-bytes")
    monkeypatch.setenv("MODEL_ARTIFACT_BASE_URL", src.as_uri())
    assert load_script().main([]) == 0
    assert artifacts.status()["ready"] and not list(env.dir.glob("*.part"))
    assert load_script().main(["--verify"]) == 0                              # full SHA-256 check passes


def test_installer_rejects_a_corrupt_download_and_installs_nothing(env, monkeypatch, capsys):
    src = env.tmp / "store"
    src.mkdir()
    for n in ("tomato_model.pth", "potato_model.pth", "yolov8n.pt"):
        (src / n).write_bytes(b"TAMPERED-bytes")                              # same length, different content
    monkeypatch.setenv("MODEL_ARTIFACT_BASE_URL", src.as_uri())
    assert load_script().main([]) == 1
    assert not any(env.dir.iterdir()) and artifacts.status()["ready"] is False


def test_installer_without_a_source_fails_clearly_and_check_mode_reports(env, capsys):
    assert load_script().main([]) == 1
    assert "MODEL_ARTIFACT_BASE_URL" in capsys.readouterr().err
    assert load_script().main(["--check"]) == 1


def test_installer_never_prints_the_token_or_url(env, monkeypatch, capsys):
    monkeypatch.setenv("MODEL_ARTIFACT_BASE_URL", (env.tmp / "does-not-exist").as_uri())
    monkeypatch.setenv("MODEL_ARTIFACT_TOKEN", "super-secret-token-123")
    load_script().main([])
    out = capsys.readouterr()
    assert "super-secret-token-123" not in out.out + out.err and "does-not-exist" not in out.out + out.err


# ── production environment validation ──────────────────────────────────────────────────────────────────────
GOOD_PROD = {"APP_ENV": "production", "ALLOWED_ORIGINS": "https://cropcast.example.app", "WEATHER_FALLBACK": "error",
             "WEATHER_PROVIDER": "open-meteo", "REQUIRE_DISEASE_MODELS": "true", "PORT": "10000"}


def test_a_complete_production_environment_passes():
    r = config_check.check_environment(GOOD_PROD)
    assert r == {"environment": "production", "errors": [], "production_gaps": [], "ok": True}


def test_empty_development_environment_is_acceptable():
    assert config_check.check_environment({})["ok"] is True


@pytest.mark.parametrize("drop,expected_fragment", [
    ("ALLOWED_ORIGINS", "ALLOWED_ORIGINS"), ("WEATHER_FALLBACK", "WEATHER_FALLBACK"), ("REQUIRE_DISEASE_MODELS", "REQUIRE_DISEASE_MODELS")])
def test_each_missing_production_requirement_is_reported(drop, expected_fragment):
    env = {k: v for k, v in GOOD_PROD.items() if k != drop}
    r = config_check.check_environment(env)
    assert r["ok"] is False and any(g.startswith(expected_fragment) for g in r["production_gaps"])


def test_wildcard_or_plain_http_origins_are_production_gaps():
    assert config_check.check_environment({**GOOD_PROD, "ALLOWED_ORIGINS": "*"})["ok"] is False
    assert config_check.check_environment({**GOOD_PROD, "ALLOWED_ORIGINS": "http://example.com"})["ok"] is False


def test_invalid_values_are_errors_and_values_are_never_echoed():
    r = config_check.check_environment({"WEATHER_FALLBACK": "banana", "PORT": "99999", "WEATHER_CACHE_TTL_S": "-3", "ALLOWED_ORIGINS": "https://secret.example"})
    assert not r["ok"] and len(r["errors"]) == 3
    assert "banana" not in json.dumps(r) and "secret.example" not in json.dumps(r)


def test_disabled_ml_method_and_unknown_providers_are_flagged():
    assert config_check.check_environment({**GOOD_PROD, "DOWNSCALING_METHOD": "ml_corrected"})["ok"] is False
    assert config_check.check_environment({"WEATHER_PROVIDER": "imd"})["errors"]


def test_env_example_is_a_valid_production_configuration_with_placeholders_only():
    values = {}
    for line in (BACKEND / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if "=" in line:
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip()
    assert config_check.check_environment(values)["ok"] is True
    assert {"APP_ENV", "ALLOWED_ORIGINS", "WEATHER_FALLBACK", "REQUIRE_DISEASE_MODELS", "MODEL_ARTIFACT_BASE_URL", "MODEL_ARTIFACT_TOKEN"} <= set(values)
    assert values["MODEL_ARTIFACT_TOKEN"] == "replace-me" and "example" in values["ALLOWED_ORIGINS"]
