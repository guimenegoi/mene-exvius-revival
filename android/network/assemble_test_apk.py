#!/usr/bin/env python3
"""Build an unsigned test base APK by replacing only two DEX files.

Input: the user's verified original Global 9.1.0 base APK and a separately
rebuilt (dev-only) APK containing the patched DEX. No game binary is checked in.
"""
from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

from patch_transport import ORIGINAL_BASE_SHA256

REPLACE = frozenset(("classes.dex", "classes3.dex"))


def assemble(original: Path, rebuilt: Path, output: Path) -> None:
    if hashlib.sha256(original.read_bytes()).hexdigest() != ORIGINAL_BASE_SHA256:
        raise ValueError("Not the pinned original FFBE Global 9.1.0 base APK")
    if output.exists():
        raise FileExistsError(f"Output must not already exist: {output}")
    if output.resolve() in (original.resolve(), rebuilt.resolve()):
        raise ValueError("Refusing to overwrite an input APK")
    with zipfile.ZipFile(original) as src, zipfile.ZipFile(rebuilt) as dex:
        original_names = src.namelist()
        if not REPLACE.issubset(original_names) or not REPLACE.issubset(dex.namelist()):
            raise ValueError("Missing target DEX in source or rebuilt APK")
        if len(original_names) != len(set(original_names)):
            raise ValueError("Original ZIP contains duplicate names")
        replacements = {name: dex.read(name) for name in REPLACE}
        if any(replacements[name] == src.read(name) for name in REPLACE):
            raise ValueError("Expected both DEX files to differ from the originals")
        with zipfile.ZipFile(output, "w", allowZip64=True) as dst:
            dst.comment = src.comment
            for entry in src.infolist():
                dst.writestr(
                    entry, replacements[entry.filename] if entry.filename in REPLACE
                    else src.read(entry.filename)
                )

    with zipfile.ZipFile(original) as src, zipfile.ZipFile(output) as dst:
        if src.namelist() != dst.namelist():
            raise ValueError("APK member set changed unexpectedly")
        changes = [
            name for name in src.namelist()
            if hashlib.sha256(src.read(name)).digest() != hashlib.sha256(dst.read(name)).digest()
        ]
        if set(changes) != REPLACE:
            raise ValueError(f"Unexpected member changes: {changes}")
    print(f"Unsigned test APK: {output}")
    print("Content changes:", ", ".join(sorted(changes)))
    print("Signature is INVALID until you sign; do not distribute this file.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--rebuilt", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    assemble(args.apk, args.rebuilt, args.out)


if __name__ == "__main__":
    main()
