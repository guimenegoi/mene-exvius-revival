"""Import-only smoke for the tracked Revival backend inside FFBE's embedded CPython.

This module is added to the *generated* stdlib.zip as ffbe_engine_bootstrap.py.
It intentionally does not call serve.main(), touch saves, or bind ports.
"""
from __future__ import annotations

import hashlib
import importlib
import io
import json
import os
import sys
import zipfile
from pathlib import Path, PurePosixPath

MANIFEST = "ffbe_engine_manifest.json"
ROOT = "ffbe_engine/"
ALLOWED = ("ios-server/", "source/server/", "android/data/",
           "data/latest.json", "vendor/yaml/", "vendor/tzdata/",
           "vendor/PIL/", "vendor/cffi/", "vendor/cryptography/",
           "vendor/pycparser/", "vendor/_cffi_backend.",
           "vendor/LICENSE-pillow.txt", "vendor/LICENSE-cffi.txt",
           "vendor/LICENSE-libffi.txt", "vendor/LICENSE-pycparser.txt",
           "vendor/LICENSE-cryptography.txt", "vendor/LICENSE-cryptography-apache.txt",
           "vendor/LICENSE-cryptography-bsd.txt",
           "vendor/LICENSE-pyyaml.txt", "vendor/LICENSE-tzdata.txt",
           "vendor/LICENSE-tzdata-apache.txt")
MAX_FILES = 1300
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
                # Android native extensions must be read-only before dlopen.
                os.chmod(temporary, 0o400 if target.suffix == '.so' else 0o600)
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
    tzdata = importlib.import_module("tzdata")
    if not Path(tzdata.__file__).resolve().is_relative_to(target_root.resolve()):
        raise RuntimeError("tzdata was not loaded from the verified private bundle")
    from datetime import datetime, timedelta
    import zoneinfo
    previous_tzpath = zoneinfo.TZPATH
    try:
        # Require the packaged tzdata rather than a device's system database.
        zoneinfo.reset_tzpath(to=())
        brazil = zoneinfo.ZoneInfo("America/Sao_Paulo")
        assert brazil.utcoffset(datetime(2026, 1, 1)) == timedelta(hours=-3)
    finally:
        zoneinfo.reset_tzpath(to=previous_tzpath)
    # Only probe Pillow if a verified Android wheel was bundled.
    imports = ["yaml", "tzdata"]
    if (target_root / "vendor/PIL/__init__.py").is_file():
        pil = importlib.import_module("PIL.Image")
        stream = io.BytesIO()
        pil.new("RGB", (2, 2), (16, 32, 64)).save(stream, format="PNG")
        stream.seek(0)
        with pil.open(stream) as image:
            assert image.size == (2, 2) and image.getpixel((0, 0)) == (16, 32, 64)
        imports.append("PIL")
    if (target_root / "vendor/cryptography/__init__.py").is_file():
        crypto = importlib.import_module("cryptography")
        if not Path(crypto.__file__).resolve().is_relative_to(target_root.resolve()):
            raise RuntimeError("cryptography not loaded from app-private bundle")
        cffi = importlib.import_module("cffi")
        pycparser = importlib.import_module("pycparser")
        assert cffi.FFI and pycparser.c_parser
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        # Independent NIST SP 800-38A AES-128-CBC known-answer vector.
        key = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
        iv = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
        plain = bytes.fromhex("6bc1bee22e409f96e93d7e117393172a")
        expected = bytes.fromhex("7649abac8119b246cee98e9b12e9197d")
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
        assert cipher.update(plain) + cipher.finalize() == expected
        from ffbe_crypto import backend, key16, cbc_encrypt, cbc_decrypt
        assert backend() == "cryptography"
        ffbe_key = key16("FFBEKey8")
        ffbe_plain = b"FFBE internal AES-128-CBC"
        assert cbc_decrypt(ffbe_key, cbc_encrypt(ffbe_key, ffbe_plain)) == ffbe_plain
        from cryptography import x509
        assert x509.CertificateBuilder
        imports.append("cryptography")
    serve = importlib.import_module("serve")
    capture = importlib.import_module("capture_server")
    if not callable(serve.configure_engine) or not hasattr(capture, "Handler"):
        raise RuntimeError("Revival server module contract is incomplete")
    return {"files": extracted, "imports": (*imports, "serve", "capture_server")}
