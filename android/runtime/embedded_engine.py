"""Import-only smoke for the tracked Revival backend inside FFBE's embedded CPython.

This module is added to the *generated* stdlib.zip as ffbe_engine_bootstrap.py.
It intentionally does not call serve.main(), touch saves, or bind ports.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
import zipfile
from pathlib import Path, PurePosixPath

MANIFEST = "ffbe_engine_manifest.json"
ROOT = "ffbe_engine/"
ALLOWED = ("ios-server/", "source/server/", "vendor/yaml/", "vendor/LICENSE-pyyaml.txt")
MAX_FILES = 400
MAX_FILE_SIZE = 24 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024


def validate_relative(name: str) -> PurePosixPath:
    if not name or name.startswith("/") or "\\" in name:
        raise ValueError("Invalid bundled engine filename")
    path = PurePosixPath(name)
    if ".." in path.parts or "." in path.parts or not any(
        name.startswith(prefix) for prefix in ALLOWED
    ):
        raise ValueError("Unexpected bundled engine path: " + name)
    return path


def install(archive: Path, target_root: Path) -> int:
    """Check manifest and SHA-256 before writing each app-private file atomically."""
    if not archive.is_file():
        raise ValueError("Missing embedded Python stdlib archive")
    with zipfile.ZipFile(archive) as zf:
        manifest = json.loads(zf.read(MANIFEST))
        files = manifest.get("files")
        if not isinstance(files, dict) or not 1 <= len(files) <= MAX_FILES:
            raise ValueError("Invalid engine bundle manifest")
        if not all(isinstance(name, str) and isinstance(value, dict)
                   for name, value in files.items()):
            raise ValueError("Invalid engine bundle entries")
        total = 0
        entries = []
        for name, info in files.items():
            validate_relative(name)
            if not isinstance(info.get("sha256"), str) or len(info["sha256"]) != 64:
                raise ValueError("Missing SHA-256 for " + name)
            if not isinstance(info.get("size"), int) or not 0 <= info["size"] <= MAX_FILE_SIZE:
                raise ValueError("Invalid engine file size")
            zip_name = ROOT + name
            entry = zf.getinfo(zip_name)
            if entry.file_size != info["size"] or entry.compress_type != zipfile.ZIP_STORED:
                raise ValueError("Unexpected embedded engine archive member")
            total += entry.file_size
            entries.append((name, zip_name, info["sha256"]))
        if total > MAX_TOTAL:
            raise ValueError("Engine bundle exceeds expected size")
        if target_root.is_symlink():
            raise ValueError("Refusing engine installation through a symlink")
        target_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        extracted = 0
        for name, zip_name, expected in entries:
            relative = validate_relative(name)
            target = target_root.joinpath(*relative.parts)
            if target.is_symlink():
                raise ValueError("Refusing to overwrite engine symlink")
            parent = target.parent
            while parent != target_root:
                if target_root not in parent.parents:
                    raise ValueError("Engine file escaped its private directory")
                if parent.is_symlink():
                    raise ValueError("Refusing symlink parent in engine tree")
                parent = parent.parent
            if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == expected:
                continue
            with zf.open(zip_name) as src:
                content = src.read(MAX_FILE_SIZE + 1)
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError("Engine source SHA-256 mismatch: " + name)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".installing")
            if temporary.is_symlink():
                raise ValueError("Refusing staging symlink")
            try:
                with temporary.open("wb") as out:
                    out.write(content)
                    out.flush()
                    os.fsync(out.fileno())
                os.chmod(temporary, 0o600)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
            extracted += 1
    return extracted


def probe(archive: Path | None = None, target_root: Path | None = None) -> dict:
    """Import only; never start the Revival engine or modify game save state."""
    if archive is None:
        archive = Path(__file__.split(".zip/")[0] + ".zip") if ".zip/" in __file__ else Path(sys.path[0])
    if target_root is None:
        target_root = archive.parent / "engine"
    extracted = install(archive, target_root)
    paths = (
        target_root / "vendor",
        target_root / "source/server",
        target_root / "ios-server",
    )
    for path in paths:
        if not path.is_dir():
            raise ValueError("Missing engine source directory: " + str(path))
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    # Do not import certs yet: cryptography's Android wheel is a separate gate.
    yaml = importlib.import_module("yaml")
    assert yaml.safe_load("enabled: true") == {"enabled": True}
    serve = importlib.import_module("serve")
    capture = importlib.import_module("capture_server")
    if not callable(serve.configure_engine) or not hasattr(capture, "Handler"):
        raise RuntimeError("Revival server module contract is incomplete")
    return {"files": extracted, "imports": ("yaml", "serve", "capture_server")}
