"""
Install / verify the disease-detection model artifacts (deployment-time; stdlib only; uploads nothing).

    python scripts/fetch_models.py --check            # report only: exit 1 if any required file is missing/wrong size
    python scripts/fetch_models.py --verify           # also SHA-256 every present file against model_manifest.json
    python scripts/fetch_models.py                    # download whatever is missing/invalid, verify, install atomically
    python scripts/fetch_models.py --write-manifest   # maintainers: (re)write model_manifest.json from the local files

Download source (environment only — nothing is hard-coded and nothing secret is ever printed):
    MODEL_ARTIFACT_BASE_URL   base URL under which each manifest `file` name can be fetched (https://, or file:// for tests)
    MODEL_ARTIFACT_TOKEN      optional bearer token sent as `Authorization: Bearer ...`
    MODEL_DIR                 destination (default backend/app/model); yolov8n.pt goes to backend/ unless MODEL_DIR is set

A downloaded file is written to a temporary name, checked against the manifest SHA-256 and size, and only then renamed
into place. A mismatch deletes the temporary file, installs nothing, and exits non-zero.
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.model import artifacts  # noqa: E402

CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def targets(manifest: dict) -> list[tuple[str, Path, dict]]:
    base = artifacts.model_dir()
    out = [(m["file"], base / m["file"], m) for m in manifest["disease_models"].values()]
    yolo = manifest.get("leaf_detector")
    if yolo:
        out.append((yolo["file"], (base if os.getenv("MODEL_DIR", "").strip() else artifacts.BACKEND_DIR) / yolo["file"], yolo))
    return out


def valid(path: Path, entry: dict, full_hash: bool) -> bool:
    if not path.is_file() or path.stat().st_size != entry["size_bytes"]:
        return False
    return (not full_hash) or sha256_of(path) == entry["sha256"]


def download(url: str, token: str | None, dest: Path, entry: dict) -> None:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=dest.name + ".", suffix=".part", dir=dest.parent)
    tmp = Path(tmp_name)
    try:
        h = hashlib.sha256()
        with os.fdopen(fd, "wb") as out, urllib.request.urlopen(req, timeout=120) as resp:
            for block in iter(lambda: resp.read(CHUNK), b""):
                out.write(block)
                h.update(block)
        if tmp.stat().st_size != entry["size_bytes"] or h.hexdigest() != entry["sha256"]:
            raise ValueError("size or SHA-256 mismatch against model_manifest.json")
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink()


def write_manifest() -> int:
    manifest = artifacts.load_manifest()
    for _, path, entry in targets(manifest):
        if not path.is_file():
            print(f"cannot write manifest: {path.name} not found", file=sys.stderr)
            return 1
        entry["size_bytes"], entry["sha256"] = path.stat().st_size, sha256_of(path)
    Path(os.getenv("MODEL_MANIFEST", "").strip() or artifacts.DEFAULT_MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("manifest updated")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--write-manifest", action="store_true")
    args = ap.parse_args(argv)
    if args.write_manifest:
        return write_manifest()

    manifest = artifacts.load_manifest()
    base_url = os.getenv("MODEL_ARTIFACT_BASE_URL", "").strip().rstrip("/")
    token = os.getenv("MODEL_ARTIFACT_TOKEN", "").strip() or None
    failures = 0
    for name, path, entry in targets(manifest):
        if valid(path, entry, full_hash=args.verify):
            print(f"ok       {name}")
            continue
        if args.check or args.verify:
            print(f"INVALID  {name} ({'missing' if not path.is_file() else 'size/hash mismatch'})")
            failures += 1
            continue
        if not base_url:
            print(f"MISSING  {name} — set MODEL_ARTIFACT_BASE_URL (and MODEL_ARTIFACT_TOKEN if private) to download", file=sys.stderr)
            failures += 1
            continue
        try:
            download(f"{base_url}/{name}", token, path, entry)
            print(f"installed {name}")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            # never echo the URL or token: report the file name and the exception class only
            print(f"FAILED   {name} ({type(exc).__name__}: {str(exc)[:80] if isinstance(exc, ValueError) else 'download error'})", file=sys.stderr)
            failures += 1
    print("all required artifacts are valid" if not failures else f"{failures} artifact(s) not available")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
