#!/usr/bin/env python3
"""Verify a cibuildwheel Android CPython 3.14 wheel before lab integration.

Architecture and wheel metadata are checked, not in-process importability.
An FFBE/Waydroid test is still required before checking a dependency as done.
No wheel, proprietary client or binary is checked into the repository.
"""
from __future__ import annotations

import argparse
import re
import zipfile
from email.parser import Parser
from pathlib import Path

from build_python_probe import ARCHIVES

EXPECTED = {
    "pillow": ("PIL/_imaging", "pillow"),
    "cryptography": ("cryptography/hazmat/bindings/_rust", "cryptography"),
}
ABI_PLATFORMS = {"arm64-v8a": "arm64_v8a", "x86_64": "x86_64"}


def check_wheel(wheel: Path, package: str, abi: str) -> dict[str, object]:
    if package not in EXPECTED or abi not in ABI_PLATFORMS:
        raise ValueError("Unsupported dependency or Android ABI")
    prefix, distribution = EXPECTED[package]
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise ValueError("Expected an existing wheel file")
    # The compiled extension uses CPython 3.14 or the stable Python ABI, never
    # a foreign CPython version such as 3.13.
    basename = wheel.name.lower().replace("-", "_")
    if not basename.startswith(distribution + "_"):
        # A proper filename is normalized by replacing separators; versions
        # are checked against dist-info/WHEEL below.
        raise ValueError("Unexpected wheel distribution")
    with zipfile.ZipFile(wheel) as zf:
        members = zf.infolist()
        if len({i.filename for i in members}) != len(members):
            raise ValueError("Duplicate wheel members")
        for member in members:
            name = member.filename
            if (name.startswith("/") or "\\" in name
                    or ".." in name.split("/") or name == ""):
                raise ValueError("Unsafe wheel member")
        meta = [i.filename for i in members if i.filename.endswith(".dist-info/WHEEL")]
        if len(meta) != 1:
            raise ValueError("Wheel metadata is missing or ambiguous")
        wheel_info = Parser().parsestr(zf.read(meta[0]).decode("utf-8"))
        tags = wheel_info.get_all("Tag", [])
        platform = ABI_PLATFORMS[abi]
        correct_platform = re.compile(rf"^android_(\d+)_{platform}$")
        valid_tags = []
        for value in tags:
            parts = value.strip().split("-")
            if len(parts) != 3:
                continue
            py, abi_tag, platform_tag = parts
            match = correct_platform.fullmatch(platform_tag)
            if not match or int(match.group(1)) > 24:
                continue
            # abi3 is compatible if its minimum Python is <= 3.14.
            stable = (abi_tag == "abi3" and re.fullmatch(r"cp3(\d+)", py)
                      and int(py[3:]) <= 14)
            native = py == "cp314" and abi_tag == "cp314"
            if stable or native:
                valid_tags.append(value)
        if not valid_tags:
            raise ValueError("Missing compatible CPython 3.14 Android wheel tag")
        native_modules = []
        for member in members:
            if not member.filename.startswith(prefix) or not member.filename.endswith(".so"):
                continue
            header = zf.read(member)[:20]
            if len(header) != 20 or header[:6] != b"\x7fELF\x02\x01":
                raise ValueError("Extension must be ELF64 little-endian")
            e_machine = int.from_bytes(header[18:20], "little")
            if e_machine != ARCHIVES[abi][2]:
                raise ValueError("Extension ELF machine mismatch")
            native_modules.append(member.filename)
        if not native_modules:
            raise ValueError("Expected native Python extension missing")
        return {
            "wheel": wheel.name,
            "tags": valid_tags,
            "native_modules": native_modules,
            "members": len(members),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--package", choices=tuple(EXPECTED), required=True)
    parser.add_argument("--abi", choices=tuple(ABI_PLATFORMS), required=True)
    args = parser.parse_args()
    result = check_wheel(args.wheel, args.package, args.abi)
    print("Android wheel structure validated:", result)
    print("NOT runtime validated: install and import inside FFBE before acceptance.")


if __name__ == "__main__":
    main()
