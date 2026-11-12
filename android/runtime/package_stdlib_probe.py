#!/usr/bin/env python3
"""Package the Python.org stdlib into an otherwise DEX-only modified test APK.

Build artifacts and proprietary APK inputs stay outside Git.
The library zip is a dev-only asset, not a complete FFBE runtime installer.
"""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

from build_python_probe import verify_archive

ASSET_NAME = "assets/ffbe_python/stdlib.zip"
DEX = {"classes.dex", "classes3.dex"}


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


def embed_asset(original: Path, dex_only: Path, output: Path, stdlib: Path) -> None:
    if output.exists():
        raise FileExistsError(output)
    if output.resolve() in (original.resolve(), dex_only.resolve()):
        raise ValueError("Refusing to overwrite an input APK")
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(dex_only) as patched:
        names = source.namelist()
        if len(set(names)) != len(names) or patched.namelist() != names:
            raise ValueError("Unexpected DEX-only base contents")
        if ASSET_NAME in names or not DEX.issubset(names):
            raise ValueError("Missing DEX or existing Python asset")
        changed = {name for name in names if source.read(name) != patched.read(name)}
        if changed != DEX:
            raise ValueError(f"Base has unexpected changes: {sorted(changed)}")
        with zipfile.ZipFile(output, "w", allowZip64=True) as dst:
            dst.comment = patched.comment
            for info in patched.infolist():
                dst.writestr(info, patched.read(info.filename))
            info = zipfile.ZipInfo(ASSET_NAME, (2026, 11, 12, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            dst.writestr(info, stdlib.read_bytes())

    with zipfile.ZipFile(original) as source, zipfile.ZipFile(output) as result:
        if result.namelist() != source.namelist() + [ASSET_NAME]:
            raise ValueError("Unexpected file set in Python test APK")
        changed = {name for name in source.namelist()
                   if source.read(name) != result.read(name)}
        if changed != DEX or result.read(ASSET_NAME) != stdlib.read_bytes():
            raise ValueError("Unexpected file content change in Python test APK")
    print("Unsigned base with Python stdlib:", output)
    print("Changes: classes.dex, classes3.dex and", ASSET_NAME)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--abi", choices=("arm64-v8a", "x86_64"), required=True)
    parser.add_argument("--python-archive", type=Path, required=True)
    parser.add_argument("--python-prefix", type=Path, required=True)
    parser.add_argument("--original-apk", type=Path, required=True)
    parser.add_argument("--dex-apk", type=Path, required=True)
    parser.add_argument("--out-apk", type=Path, required=True)
    parser.add_argument("--out-stdlib", type=Path, required=True)
    args = parser.parse_args()
    verify_archive(args.python_archive, args.abi)
    pack_stdlib(args.python_prefix, args.out_stdlib)
    embed_asset(args.original_apk, args.dex_apk, args.out_apk, args.out_stdlib)
    print("Lab only: does not contain a server, saves, or complete offline data.")


if __name__ == "__main__":
    main()
