#!/usr/bin/env python3
"""Package the Python.org stdlib into an otherwise DEX-only modified test APK.

Build artifacts and proprietary APK inputs stay outside Git.
The library zip is a dev-only asset, not a complete FFBE runtime installer.
"""
from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path

from build_python_probe import verify_archive, verify_elf

ASSET_NAME = "assets/ffbe_python/stdlib.zip"
NATIVE_INDEX = "assets/ffbe_python/dynload-index.txt"
NATIVE_PREFIX = "assets/ffbe_python/dynload/"
DEX = {"classes.dex", "classes3.dex"}


def native_assets(prefix: Path, abi: str) -> dict[str, bytes]:
    """Read official CPython Android .so modules with pinned ABI and safe basenames."""
    directory = prefix / "lib/python3.14/lib-dynload"
    if not directory.is_dir():
        raise ValueError("Python.org lib-dynload folder missing")
    modules = sorted(directory.glob("*.so"))
    if not 1 <= len(modules) <= 128:
        raise ValueError("Unexpected number of native stdlib modules")
    assets = {}
    for file in modules:
        if file.is_symlink() or not re.fullmatch(r"[A-Za-z0-9_.-]+\.so", file.name):
            raise ValueError(f"Unsafe native module basename: {file.name}")
        verify_elf(file, abi)
        assets[NATIVE_PREFIX + file.name] = file.read_bytes()
    if not any(name.startswith(NATIVE_PREFIX + "_ssl.") for name in assets):
        raise ValueError("Missing _ssl native extension")
    assets[NATIVE_INDEX] = ("\n".join(file.name for file in modules) + "\n").encode("ascii")
    return assets


def pack_stdlib(prefix: Path, output: Path) -> None:
    root = prefix / "lib/python3.14"
    if not (root / "encodings/__init__.py").is_file():
        raise ValueError("Python.org standard library is missing")
    if output.exists():
        raise FileExistsError(output)
    paths = sorted(p for p in root.rglob("*.py") if p.is_file()
                   and not p.is_symlink() and "__pycache__" not in p.parts
                   and "site-packages" not in p.parts)
    if not paths:
        raise ValueError("No stdlib source files")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", allowZip64=True) as dst:
        for path in paths:
            name = path.relative_to(root).as_posix()
            if name.startswith("../") or name.startswith("/"):
                raise ValueError("Unsafe Python stdlib file name")
            info = zipfile.ZipInfo(name, (2026, 11, 12, 0, 0, 0))
            # zipimport needs zlib for DEFLATE, but zlib is not yet importable
            # during CPython's bootstrap from this ZIP. Use stored entries.
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            dst.writestr(info, path.read_bytes())
    with zipfile.ZipFile(output) as zf:
        if not {"encodings/__init__.py", "json/__init__.py"}.issubset(zf.namelist()):
            raise ValueError("Incomplete Python standard library archive")
    print("Python stdlib source archive:", output, output.stat().st_size, "bytes")


def embed_asset(original: Path, dex_only: Path, output: Path, stdlib: Path,
                additional_assets: dict[str, bytes] | None = None) -> None:
    if output.exists():
        raise FileExistsError(output)
    if output.resolve() in (original.resolve(), dex_only.resolve()):
        raise ValueError("Refusing to overwrite an input APK")
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(dex_only) as patched:
        names = source.namelist()
        if len(set(names)) != len(names) or patched.namelist() != names:
            raise ValueError("Unexpected DEX-only base contents")
        added = {ASSET_NAME: stdlib.read_bytes(), **(additional_assets or {})}
        if ASSET_NAME in names or any(name in names for name in added) or not DEX.issubset(names):
            raise ValueError("Missing DEX or existing Python asset")
        if any(not name.startswith("assets/ffbe_python/") for name in added):
            raise ValueError("Python assets must stay under private asset prefix")
        changed = {name for name in names if source.read(name) != patched.read(name)}
        if changed != DEX:
            raise ValueError(f"Base has unexpected changes: {sorted(changed)}")
        with zipfile.ZipFile(output, "w", allowZip64=True) as dst:
            dst.comment = patched.comment
            for info in patched.infolist():
                dst.writestr(info, patched.read(info.filename))
            for asset, payload in added.items():
                info = zipfile.ZipInfo(asset, (2026, 11, 12, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = 0o100644 << 16
                dst.writestr(info, payload)

    with zipfile.ZipFile(original) as source, zipfile.ZipFile(output) as result:
        if result.namelist() != source.namelist() + list(added):
            raise ValueError("Unexpected file set in Python test APK")
        changed = {name for name in source.namelist()
                   if source.read(name) != result.read(name)}
        if changed != DEX or any(result.read(k) != value for k, value in added.items()):
            raise ValueError("Unexpected file content change in Python test APK")
    print("Unsigned base with Python stdlib:", output)
    print("Changes: classes.dex, classes3.dex plus", len(added), "Python assets")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--abi", choices=("arm64-v8a", "x86_64"), required=True)
    parser.add_argument("--python-archive", type=Path, required=True)
    parser.add_argument("--python-prefix", type=Path, required=True)
    parser.add_argument("--original-apk", type=Path, required=True)
    parser.add_argument("--dex-apk", type=Path, required=True)
    parser.add_argument("--out-apk", type=Path, required=True)
    parser.add_argument("--out-stdlib", type=Path, required=True)
    parser.add_argument("--native-extensions", action="store_true",
                        help="bundle official CPython Android lib-dynload assets")
    args = parser.parse_args()
    verify_archive(args.python_archive, args.abi)
    pack_stdlib(args.python_prefix, args.out_stdlib)
    extras = native_assets(args.python_prefix, args.abi) if args.native_extensions else None
    embed_asset(args.original_apk, args.dex_apk, args.out_apk, args.out_stdlib, extras)
    print("Lab only: does not contain a server, saves, or complete offline data.")


if __name__ == "__main__":
    main()
