#!/usr/bin/env python3
"""Rebuild the embedded FFBE Python engine without mixing code revisions.

The base APK is an already split-merged, UNsigned (or previously signed)
ARM64 RC2 package. This script never publishes or installs the output.
After running it, the original signer MUST re-sign and verify the APK.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ASSET = "assets/ffbe_python/stdlib.zip"
PACK_FIELDS = ("id", "sha256", "size", "unpackedSize")

def tracked_sources(repo: Path) -> dict[str, bytes]:
    raw = subprocess.check_output([
        "git", "-C", str(repo), "ls-files", "-z", "--",
        "source/server", "ios-server", "android/data/offline_data.py",
        "data/latest.json",
    ])
    files = {}
    for part in raw.split(b"\0"):
        if not part:
            continue
        name = part.decode("utf-8")
        if not (
            name.startswith("source/server/")
            or name.startswith("ios-server/") and name.endswith(".py")
            or name in ("android/data/offline_data.py", "data/latest.json")
        ):
            continue
        file = repo / name
        if not file.is_file() or file.is_symlink():
            raise ValueError("Unsafe missing repository file: " + name)
        files[name] = file.read_bytes()
    if not 100 <= len(files) <= 500 or "source/server/offline_menu.py" not in files:
        raise ValueError("Unexpected FFBE backend module inventory")
    return files

def verify_pinned_downloads(embedded: dict, repository: dict) -> None:
    for key in ("schema", "revision", "version", "files", "downloadBytes", "installedBytes"):
        if embedded[key] != repository[key]:
            raise ValueError("Pinned game pack set differs: " + key)
    for item, new in zip(embedded["packs"], repository["packs"]):
        if tuple(item[k] for k in PACK_FIELDS) != tuple(new[k] for k in PACK_FIELDS):
            raise ValueError("Pinned pack hash/length differs")
    if len(embedded["packs"]) != len(repository["packs"]) or len(embedded["packs"]) != 19:
        raise ValueError("Expected exactly 19 pinned game packs")

def build(repo: Path, base: Path, output: Path, *, with_backup=False,
          with_restore=False) -> dict:
    repo, base, output = map(Path, (repo, base, output))
    if base.resolve() == output.resolve():
        raise ValueError("Never overwrite base APK")
    if not base.is_file():
        raise ValueError("Missing merged base APK")
    if output.exists():
        raise ValueError("Refusing to overwrite existing APK")
    sources = tracked_sources(repo)
    replacements = {"ffbe_engine/" + key: value for key, value in sources.items()}
    replacements.update({
        "ffbe_engine_bootstrap.py": (repo / "android/runtime/embedded_engine.py").read_bytes(),
        "ffbe_local_http.py": (repo / "android/runtime/local_http.py").read_bytes(),
    })
    if with_restore and not with_backup:
        raise ValueError("Restore experiment requires the optional backup client")
    if with_restore:
        replacements["ffbe_restore_startup.py"] = (
            repo / "android/runtime/restore_startup.py").read_bytes()
        replacements["ffbe_save_restore.py"] = (
            repo / "android/backup/save_restore.py").read_bytes()
    if with_backup:
        replacements["ffbe_backup.py"] = (repo / "android/backup/embedded_client.py").read_bytes()
        replacements["ffbe_backup_transport.py"] = (repo / "android/backup/lxc_backup.py").read_bytes()
        replacements["config_model.py"] = (repo / "android/backup/config_model.py").read_bytes()
        replacements["config_service.py"] = (repo / "android/backup/config_service.py").read_bytes()
        replacements["config_sync.py"] = (repo / "android/backup/config_sync.py").read_bytes()
        if "BackupCoordinator" not in replacements["ffbe_backup.py"].decode("utf-8"):
            raise ValueError("Expected experimental Android backup client")

    output.parent.mkdir(parents=True, exist_ok=True)
    fd, nested_tmp = tempfile.mkstemp(suffix=".zip", dir=output.parent)
    os.close(fd)
    nested = Path(nested_tmp)
    temporary_output = output.with_name(output.name + ".building")
    try:
        with zipfile.ZipFile(base) as outer, zipfile.ZipFile(outer.open(ASSET)) as inner:
            pinned = json.loads(inner.read("ffbe_offline_manifest.json"))
            repo_manifest = json.loads((repo / "data/latest.json").read_bytes())
            verify_pinned_downloads(pinned, repo_manifest)
            manifest = json.loads(inner.read("ffbe_engine_manifest.json"))
            for name, content in sources.items():
                manifest["files"][name] = {
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size": len(content),
                }
            replacements["ffbe_engine_manifest.json"] = (
                json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
            absent = set(replacements)
            with zipfile.ZipFile(nested, "w", allowZip64=True) as target:
                for info in inner.infolist():
                    content = replacements.get(info.filename)
                    if content is None:
                        content = inner.read(info.filename)
                    else:
                        absent.discard(info.filename)
                    target.writestr(info, content)
                for name in sorted(absent):
                    info = zipfile.ZipInfo(name, (2026, 11, 13, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_STORED
                    info.external_attr = 0o100644 << 16
                    target.writestr(info, replacements[name])
        with zipfile.ZipFile(nested) as check:
            for name, content in replacements.items():
                item = check.getinfo(name)
                if item.compress_type != zipfile.ZIP_STORED or check.read(item) != content:
                    raise ValueError("Invalid or compressed embedded module: " + name)
            record = json.loads(check.read("ffbe_engine_manifest.json"))
            if len(record["files"]) > 1300:
                raise ValueError("Engine exceeds bootstrap file cap")
            for name, metadata in record["files"].items():
                item = check.getinfo("ffbe_engine/" + name)
                if item.compress_type != zipfile.ZIP_STORED or item.file_size != metadata["size"]:
                    raise ValueError("Engine manifest size/storage mismatch: " + name)
                if hashlib.sha256(check.read(item)).hexdigest() != metadata["sha256"]:
                    raise ValueError("Engine manifest SHA-256 mismatch: " + name)
        with zipfile.ZipFile(base) as original, zipfile.ZipFile(temporary_output, "w", allowZip64=True) as assembled:
            embedded_data = nested.read_bytes()
            for item in original.infolist():
                assembled.writestr(item, embedded_data if item.filename == ASSET else original.read(item.filename))
        with zipfile.ZipFile(temporary_output) as test:
            with zipfile.ZipFile(test.open(ASSET)) as embedded:
                if embedded.read("ffbe_engine_bootstrap.py") != replacements["ffbe_engine_bootstrap.py"]:
                    raise ValueError("APK bootstrap not replaced")
                if with_backup and not all(k in embedded.namelist()
                                           for k in ("ffbe_backup.py", "ffbe_backup_transport.py",
                                                     "config_model.py", "config_service.py",
                                                     "config_sync.py")):
                    raise ValueError("Missing embedded backup dependencies")
                if with_restore and not all(k in embedded.namelist()
                                            for k in ("ffbe_restore_startup.py",
                                                      "ffbe_save_restore.py")):
                    raise ValueError("Missing experimental restore dependencies")
        temporary_output.replace(output)
    finally:
        nested.unlink(missing_ok=True)
        temporary_output.unlink(missing_ok=True)
    return {
        "base": str(base),
        "apk": str(output),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "backend_files": len(sources),
        "backup_experimental": with_backup,
        "restore_experimental": with_restore,
        "signed": False,
    }

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--experimental-backup", action="store_true")
    p.add_argument("--experimental-restore", action="store_true",
                   help="embed offline-only recovery guard; requires experimental backup")
    args = p.parse_args(argv)
    print(json.dumps(build(args.repo, args.base, args.out,
                           with_backup=args.experimental_backup,
                           with_restore=args.experimental_restore),
                     indent=2), flush=True)

if __name__ == "__main__":
    main()
