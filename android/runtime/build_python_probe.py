#!/usr/bin/env python3
"""Build a dev-only JNI CPython probe and inject libraries into an ABI split.

No APK, Python distribution, NDK, signing key, or binary is committed.
The bridge exposes Py_GetVersion and an isolated code-execution smoke probe.
Neither runs the Revival backend or implements a production lifecycle.
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import subprocess
import zipfile
from pathlib import Path

PYTHON_VERSION = "3.14.10"
ARCHIVES = {
    "arm64-v8a": (
        "aarch64", "aarch64-linux-android24-clang", 183,
        "423c80b957330cf0ebb92b9b20f2294c292144a441bdb0ceb8c69d14928e569b",
    ),
    "x86_64": (
        "x86_64", "x86_64-linux-android24-clang", 62,
        "6ebda1fc3f28efc5861cad397254e8ce5d81ba4f83a3cb6a0c124c3826a0e14c",
    ),
}
SO = "libffbe_python_probe.so"
LIBPYTHON = "libpython3.14.so"
SOURCE = Path(__file__).parent / "native/python_probe.c"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_archive(path: Path, abi: str) -> None:
    arch, _, _, expected = ARCHIVES[abi]
    if path.name != f"python-{PYTHON_VERSION}-{arch}-linux-android.tar.gz":
        raise ValueError("Unexpected Python.org distribution filename")
    if digest(path) != expected:
        raise ValueError(f"Python.org {abi} package SHA-256 mismatch")


def elf_machine(path: Path) -> int:
    with path.open("rb") as stream:
        header = stream.read(20)
    if len(header) != 20 or header[:6] != b"\x7fELF\x02\x01":
        raise ValueError(f"Not ELF64 little-endian: {path}")
    return struct.unpack_from("<H", header, 18)[0]


def verify_elf(path: Path, abi: str) -> None:
    expected = ARCHIVES[abi][2]
    if elf_machine(path) != expected:
        raise ValueError(f"Unexpected ELF machine for {abi}: {path}")


def compile_probe(prefix: Path, ndk: Path, abi: str, output: Path) -> None:
    _, cc_name, _, _ = ARCHIVES[abi]
    compiler = (ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin" / cc_name)
    headers = prefix / "include/python3.14"
    library = prefix / "lib" / LIBPYTHON
    if not compiler.is_file() or not headers.is_dir():
        raise ValueError("Missing Android NDK compiler or Python.org headers")
    verify_elf(library, abi)
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(compiler), "-std=c11", "-O2", "-fPIC", "-shared",
        "-Wl,-z,relro", "-Wl,-z,now", f"-Wl,-soname,{SO}",
        "-I", str(headers), "-L", str(prefix / "lib"),
        str(SOURCE), str(SOURCE.parent / "native_assets.c"),
        "-lpython3.14", "-landroid", "-llog", "-o", str(output),
    ]
    subprocess.run(command, check=True)
    verify_elf(output, abi)


def embed_split(original: Path, output: Path, abi: str, native_so: Path,
                python_so: Path, extra_libs: dict[str, Path] | None = None) -> None:
    """Preserve every original member and only add two ABI-matched libraries."""
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    if output.resolve() == original.resolve():
        raise ValueError("Refusing to overwrite the user's original split")
    verify_elf(native_so, abi)
    verify_elf(python_so, abi)
    new_members = {
        f"lib/{abi}/{SO}": native_so.read_bytes(),
        f"lib/{abi}/{LIBPYTHON}": python_so.read_bytes(),
    }
    for filename, source in (extra_libs or {}).items():
        if filename not in {"libcrypto_python.so", "libssl_python.so", "libsqlite3_python.so"}:
            raise ValueError("Unexpected Android Python dependency library")
        verify_elf(source, abi)
        new_members[f"lib/{abi}/{filename}"] = source.read_bytes()
    with zipfile.ZipFile(original) as src:
        names = src.namelist()
        if len(set(names)) != len(names) or any(n in names for n in new_members):
            raise ValueError("Unexpected or previously injected split content")
        if f"lib/{abi}/libgame.so" not in names:
            raise ValueError("Split does not match requested game ABI")
        with zipfile.ZipFile(output, "w", allowZip64=True) as dst:
            dst.comment = src.comment
            for info in src.infolist():
                dst.writestr(info, src.read(info.filename))
            for name, value in new_members.items():
                info = zipfile.ZipInfo(name, (2026, 11, 12, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = 0o100644 << 16
                dst.writestr(info, value)

    with zipfile.ZipFile(original) as src, zipfile.ZipFile(output) as dst:
        if dst.namelist() != src.namelist() + list(new_members):
            raise ValueError("Unexpected ABI split member changes")
        if any(src.read(name) != dst.read(name) for name in src.namelist()):
            raise ValueError("Existing split members mutated")
        if any(dst.read(name) != content for name, content in new_members.items()):
            raise ValueError("Injected libraries changed")
    print("Unsigned ABI test split:", output)
    print("Added:", ", ".join(new_members))
    print("Original ABI split entries preserved; signing still required.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--abi", required=True, choices=tuple(ARCHIVES))
    parser.add_argument("--python-archive", type=Path, required=True)
    parser.add_argument("--python-prefix", type=Path, required=True)
    parser.add_argument("--ndk", type=Path, required=True)
    parser.add_argument("--original-split", type=Path, required=True)
    parser.add_argument("--output-split", type=Path, required=True)
    parser.add_argument("--output-so", type=Path, required=True)
    parser.add_argument("--extra-native-libs", action="store_true",
                        help="embed official Python.org ssl/crypto/sqlite Android libs")
    args = parser.parse_args()
    verify_archive(args.python_archive, args.abi)
    compile_probe(args.python_prefix, args.ndk, args.abi, args.output_so)
    extras = ({name: args.python_prefix / "lib" / name for name in
               ("libcrypto_python.so", "libssl_python.so", "libsqlite3_python.so")}
              if args.extra_native_libs else None)
    embed_split(
        args.original_split, args.output_split, args.abi,
        args.output_so, args.python_prefix / "lib" / LIBPYTHON, extras,
    )
    print("DEV PROBE ONLY: Python version/isolated-code test, no Revival server.")


if __name__ == "__main__":
    main()
