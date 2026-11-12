#!/usr/bin/env python3
"""Complete, single-tree FFBE data setup for the future self-contained Android APK.

Reuses the Revival fetch_data installer for the existing 18 server/native packs.
Adds the one client-assets pack omitted by the iOS/desktop server installer.
No Termux, APK patch, VPN, or device-specific paths are required by this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "ios-server"))
import fetch_data  # noqa: E402

MANIFEST = REPO / "data/latest.json"
ASSET_FILE = "static/client/game-assets.apk"
ASSET_RECEIPT = "offline-client-assets.json"
REQUIRED_FILES = (
    "static/mst_decoded/F_UNIT_MST.ndjson",
    "static/mst_decoded/F_MISSION_MST.ndjson",
    "static/client/shared_prefs/gamedata.xml",
    ASSET_FILE,
)
REQUIRED_GROUPS = (
    ("native/mst", "*.dat"),
    ("native/localized_texts/en", "*.dat"),
    ("native/en/sd/area", "*.cpk"),
    ("native/common_lang", "**/*.cpk"),
    ("static/text_decoded", "*"),
)


def digest(path: Path) -> str:
    return fetch_data.sha256(path)


def read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return result


def atomic_json(path: Path, value: dict) -> None:
    temp = path.with_name(path.name + ".writing")
    with temp.open("w", encoding="utf-8") as out:
        json.dump(value, out, indent=2, sort_keys=True)
        out.write("\n")
    temp.replace(path)


def manifest_from(path: Path) -> tuple[dict, dict]:
    manifest = read_json(path)
    if manifest.get("schema") != 1:
        raise ValueError("Unsupported data manifest schema")
    packs = manifest.get("packs")
    if not isinstance(packs, list) or not packs:
        raise ValueError("Data manifest has no packs")
    ids: set[str] = set()
    for pack in packs:
        if not isinstance(pack, dict):
            raise ValueError("Invalid data pack")
        name, expected, size = pack.get("id"), pack.get("sha256"), pack.get("size")
        if not isinstance(name, str) or not name or "/" in name or "\\" in name or ".." in name:
            raise ValueError("Unsafe pack ID")
        if name in ids:
            raise ValueError(f"Duplicate pack ID: {name}")
        ids.add(name)
        if not isinstance(expected, str) or len(expected) != 64 or any(
            c not in "0123456789abcdef" for c in expected
        ):
            raise ValueError(f"Invalid SHA-256 for {name}")
        if not isinstance(size, int) or size <= 0:
            raise ValueError(f"Invalid size for {name}")
        if not isinstance(pack.get("url"), str) or not pack["url"]:
            raise ValueError(f"Missing download URL for {name}")
    if "client-assets" not in ids:
        raise ValueError("Manifest does not contain client-assets")
    client = next(pack for pack in packs if pack["id"] == "client-assets")
    return manifest, client


def backend_changed(manifest: dict, installed: dict) -> list[dict]:
    # Later packs overwrite earlier ones; follow fetch_data.main() exactly.
    packs = [pack for pack in manifest["packs"] if pack["id"] not in fetch_data.SKIP]
    first = next(
        (i for i, pack in enumerate(packs) if installed.get(pack["id"]) != pack["sha256"]),
        None,
    )
    return packs[first:] if first is not None else []


def plan(manifest: dict, data: Path) -> tuple[list[dict], dict | None]:
    installed = read_json(data / "installed.json")
    server = backend_changed(manifest, installed)
    client = next(pack for pack in manifest["packs"] if pack["id"] == "client-assets")
    receipt = read_json(data / ASSET_RECEIPT)
    asset = data / ASSET_FILE
    valid_client = (
        installed.get("client-assets") == client["sha256"]
        and receipt.get("archive_sha256") == client["sha256"]
        and receipt.get("file") == ASSET_FILE
        and asset.is_file()
        and asset.stat().st_size == receipt.get("file_size")
        and digest(asset) == receipt.get("file_sha256")
    )
    return server, None if valid_client else client


def install_client(data: Path, pack: dict) -> None:
    downloads = data / ".downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    archive = downloads / "client-assets.zip"
    if archive.exists() and (archive.stat().st_size != pack["size"] or digest(archive) != pack["sha256"]):
        archive.unlink()
    if not archive.exists():
        fetch_data.download(pack["url"], archive, pack["size"])
    if digest(archive) != pack["sha256"]:
        archive.unlink()
        raise ValueError("client-assets SHA-256 mismatch; retry the installation")
    with zipfile.ZipFile(archive) as zf:
        members = [i for i in zf.infolist() if not i.is_dir()]
        if len(members) != 1 or members[0].filename != ASSET_FILE:
            raise ValueError("Unexpected client-assets layout")
        if members[0].file_size <= 0:
            raise ValueError("Empty client game asset archive")
        # The entire outer ZIP was already authenticated against the manifest.
        content_hash = hashlib.sha256()
        with zf.open(members[0]) as stream:
            for block in iter(lambda: stream.read(4 << 20), b""):
                content_hash.update(block)
        expected_file_hash = content_hash.hexdigest()
        expected_size = members[0].file_size

    # fetch_data.destination validates the member path and uses the canonical
    # DATA/static tree. No second copy for the server is introduced.
    count = fetch_data.unpack(archive)
    if count != 1:
        raise ValueError("client-assets extraction produced unexpected file count")
    target = data / ASSET_FILE
    if target.stat().st_size != expected_size or digest(target) != expected_file_hash:
        raise ValueError("Extracted client assets do not match the verified pack")
    atomic_json(
        data / ASSET_RECEIPT,
        {
            "archive_sha256": pack["sha256"],
            "file": ASSET_FILE,
            "file_sha256": expected_file_hash,
            "file_size": expected_size,
        },
    )
    installed = read_json(data / "installed.json")
    installed[pack["id"]] = pack["sha256"]
    atomic_json(data / "installed.json", installed)
    archive.unlink()


def verify(manifest: dict, data: Path) -> list[str]:
    errors: list[str] = []
    installed = read_json(data / "installed.json")
    for pack in manifest["packs"]:
        if installed.get(pack["id"]) != pack["sha256"]:
            errors.append(f"pack not installed/current: {pack['id']}")
    for path in REQUIRED_FILES:
        p = data / path
        if not p.is_file() or p.stat().st_size == 0:
            errors.append(f"missing or empty: {path}")
    for folder, pattern in REQUIRED_GROUPS:
        p = data / folder
        if not p.is_dir() or not any(x.is_file() and x.stat().st_size > 0 for x in p.glob(pattern)):
            errors.append(f"missing group: {folder}/{pattern}")

    # The manifest's `files` count covers the canonical native/static trees
    # and registry.json, but not install receipts, saves, caches or logs.
    # Extra generated files are allowed; fewer files indicates an incomplete
    # first install even if all per-pack markers were written.
    expected_files = manifest.get("files")
    if isinstance(expected_files, int) and expected_files > 0:
        # Native may be a link to Android getFilesDir(); count ONLY the five
        # native roots or os.walk would also traverse exvius/data/static twice.
        roots = [data / "native" / name for name in sorted(fetch_data.NATIVE_TOPS)]
        roots.append(data / "static")
        actual = sum(
            len(files)
            for root in roots
            if root.is_dir()
            for _, dirs, files in os.walk(root)
        ) + int((data / "registry.json").is_file())
        if actual < expected_files:
            errors.append(f"incomplete file inventory: {actual} / {expected_files}")

    pack = next(p for p in manifest["packs"] if p["id"] == "client-assets")
    receipt = read_json(data / ASSET_RECEIPT)
    asset = data / ASSET_FILE
    if receipt.get("archive_sha256") != pack["sha256"] or receipt.get("file") != ASSET_FILE:
        errors.append("missing/obsolete client asset receipt")
    elif asset.is_file():
        if asset.stat().st_size != receipt.get("file_size"):
            errors.append("client asset size changed")
        elif digest(asset) != receipt.get("file_sha256"):
            errors.append("client asset hash changed")
    return errors


def free_bytes(data: Path) -> int:
    existing = data
    while not existing.exists():
        parent = existing.parent
        if parent == existing:
            raise ValueError(f"No accessible parent filesystem for {data}")
        existing = parent
    return shutil.disk_usage(existing).free


def minimum_free(manifest: dict, data: Path, server: list[dict], client: dict | None) -> int:
    if not server and client is None:
        return 0
    installed = read_json(data / "installed.json")
    current_server = [p for p in manifest["packs"] if p["id"] not in fetch_data.SKIP]
    fresh = server and not any(p["id"] in installed for p in current_server)
    if fresh:
        # Fresh installs must fit the final extracted tree, the largest
        # temporary ZIP and a 2-GiB reserve. For the real FFBE release,
        # retain the established conservative 22-GiB requirement.
        total = sum(p.get("unpackedSize", p["size"]) for p in manifest["packs"])
        largest = max(p["size"] for p in manifest["packs"])
        needed = total + largest + (2 << 30)
        return max(needed, 22 << 30) if total >= (1 << 30) else needed
    if server:
        # Incremental packs are unpacked one at a time in the existing tree.
        return max(p["size"] + p.get("unpackedSize", p["size"]) for p in server) + (1 << 30)
    return client["size"] + client.get("unpackedSize", client["size"]) + (128 << 20)


def android_files_layout(data: Path, client_files: Path, create: bool) -> None:
    """Map only the five native data folders to the original game file root.

    Android getFilesDir(): <files>/{mst,en,common_lang,...}
    Server data root:     <files>/exvius/data/{static,native}
    Only DATA/native/<whitelisted> is linked; never expose the complete
    application-private files directory as the server's CDN_ROOT.
    """
    files = client_files.expanduser().resolve()
    required = files / "exvius" / "data"
    if data != required:
        raise ValueError(f"Expected --data {required} when --android-files is set")
    native = data / "native"
    if native.is_symlink() or (native.exists() and not native.is_dir()):
        raise ValueError(f"Refusing unsafe native root: {native}")
    names = sorted(fetch_data.NATIVE_TOPS)
    if native.exists():
        unexpected = set(x.name for x in native.iterdir()) - set(names)
        if unexpected:
            raise ValueError(f"Refusing unexpected native entries: {sorted(unexpected)}")
    absent = []
    for name in names:
        link = native / name
        target = files / name
        if link.is_symlink():
            if link.resolve() != target:
                raise ValueError(f"Refusing foreign native link: {link}")
        elif link.exists():
            raise ValueError(f"Refusing to replace an existing native tree: {link}")
        else:
            absent.append(name)
    if create:
        # pathlib.mkdir() does not treat a dangling symlink as a directory.
        # Prepare actual game folders *before* linking the server's view.
        for name in names:
            target = files / name
            if target.is_symlink() or (target.exists() and not target.is_dir()):
                raise ValueError(f"Refusing unsafe game resource path: {target}")
        files.mkdir(parents=True, exist_ok=True)
        for name in names:
            (files / name).mkdir(exist_ok=True)
        native.mkdir(parents=True, exist_ok=True)
        for name in absent:
            link = native / name
            link.symlink_to("../../../" + name, target_is_directory=True)
            if link.resolve() != files / name:
                link.unlink(missing_ok=True)
                raise ValueError(f"Native link for {name} is not in game storage")

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=("plan", "install", "verify"))
    parser.add_argument("--data", type=Path, required=True, help="one private data root shared by the game and Revival")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--android-files", type=Path, help="the app-private Context.getFilesDir() root; share native files without copying")
    args = parser.parse_args(argv)
    data = args.data.expanduser().resolve()
    if args.android_files is not None:
        android_files_layout(data, args.android_files, create=False)
    manifest_path = args.manifest.expanduser().resolve()
    manifest, client = manifest_from(manifest_path)
    fetch_data.DATA = data
    server, missing_client = plan(manifest, data)

    if args.action == "plan":
        needed = sum(p["size"] for p in server) + (missing_client["size"] if missing_client else 0)
        print(
            f"Revision {manifest.get('version')} | packs {len(manifest['packs'])} | "
            f"download remaining {needed / 1e9:.2f} GB"
        )
        print(f"Server packs to install/reapply: {len(server)}; client assets: {'yes' if missing_client else 'no'}")
        print(f"Total installed data advertised: {manifest.get('installedBytes', 0) / 1e9:.2f} GB")
        print(f"Free disk: {free_bytes(data) / (1 << 30):.1f} GiB; recommended available: "
              f"{minimum_free(manifest, data, server, missing_client) / (1 << 30):.1f} GiB")
        return 0

    if args.action == "install":
        required = minimum_free(manifest, data, server, missing_client)
        available = free_bytes(data)
        if available < required:
            print(f"Insufficient free storage: {available / (1 << 30):.2f} GiB; "
                  f"require {required / (1 << 30):.2f} GiB")
            return 2
        data.mkdir(parents=True, exist_ok=True)
        if args.android_files is not None:
            android_files_layout(data, args.android_files, create=True)
        # Downloading one pack at a time avoids keeping 14+ GB of compressed
        # archives alongside the final extracted files.
        if server:
            result = fetch_data.main(["--manifest", str(manifest_path)])
            if result != 0:
                return result
        if missing_client:
            print("Installing client-assets using the existing verified pack downloader")
            install_client(data, client)
        print("Installation phase finished; checking offline data readiness")

    errors = verify(manifest, data)
    for error in errors:
        print(f"FAIL {error}")
    if errors:
        print(f"Offline data incomplete: {len(errors)} issue(s)")
        return 1
    print("All manifest packs installed; essential game and client assets present.")
    print("NOTE: runtime integration and disconnected gameplay still require separate validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
