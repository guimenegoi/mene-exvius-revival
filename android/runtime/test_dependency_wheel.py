#!/usr/bin/env python3
"""Contract tests for Android CPython 3.14 wheel gates."""
from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from verify_dependency_wheel import check_wheel


def elf(machine: int) -> bytes:
    return b"\x7fELF\x02\x01" + b"\0" * 12 + machine.to_bytes(2, "little") + b"x"


def wheel(path: Path, *, tag: str, entry: str, machine: int = 183,
          duplicate: bool = False) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("pillow-13.0.0.dist-info/WHEEL",
                    "Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: " + tag + "\n")
        zf.writestr(entry, elf(machine))
        if duplicate:
            zf.writestr(entry, elf(machine))


class DependencyWheelTests(unittest.TestCase):
    def test_valid_cp314_arm64_native_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "pillow-13.0.0-cp314-cp314-android_24_arm64_v8a.whl"
            wheel(archive, tag="cp314-cp314-android_24_arm64_v8a",
                  entry="PIL/_imaging.cpython-314-aarch64-linux-android.so")
            result = check_wheel(archive, "pillow", "arm64-v8a")
            self.assertEqual(len(result["native_modules"]), 1)

    def test_valid_stable_abi3(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "cryptography-50.0.2-cp39-abi3-android_24_arm64_v8a.whl"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("cryptography-50.0.2.dist-info/WHEEL",
                            "Wheel-Version: 1.0\nTag: cp39-abi3-android_24_arm64_v8a\n")
                zf.writestr("cryptography/hazmat/bindings/_rust.abi3.so", elf(183))
            self.assertTrue(check_wheel(archive, "cryptography", "arm64-v8a")["tags"])


    def test_cffi_backend_arm64(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "cffi-2.1.1-cp314-cp314-android_24_arm64_v8a.whl"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("cffi-2.1.1.dist-info/WHEEL",
                            "Wheel-Version: 1.0\nTag: cp314-cp314-android_24_arm64_v8a\n")
                zf.writestr("_cffi_backend.cpython-314-aarch64-linux-android.so",
                            elf(183))
            result = check_wheel(archive, "cffi", "arm64-v8a")
            self.assertEqual(len(result["native_modules"]), 1)

    def test_wrong_python_abi_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "pillow-13.0.0-cp313-cp313-android_24_arm64_v8a.whl"
            wheel(archive, tag="cp313-cp313-android_24_arm64_v8a",
                  entry="PIL/_imaging.cpython-313.so")
            with self.assertRaisesRegex(ValueError, "compatible CPython"):
                check_wheel(archive, "pillow", "arm64-v8a")

    def test_wrong_elf_architecture_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "pillow-13.0.0-cp314-cp314-android_24_arm64_v8a.whl"
            wheel(archive, tag="cp314-cp314-android_24_arm64_v8a",
                  entry="PIL/_imaging.cpython-314.so", machine=62)
            with self.assertRaisesRegex(ValueError, "ELF machine mismatch"):
                check_wheel(archive, "pillow", "arm64-v8a")

    def test_linux_only_wheel_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "pillow-13.0.0-cp314-cp314-manylinux_x86_64.whl"
            wheel(archive, tag="cp314-cp314-manylinux_x86_64",
                  entry="PIL/_imaging.cpython-314.so")
            with self.assertRaisesRegex(ValueError, "Android wheel tag"):
                check_wheel(archive, "pillow", "arm64-v8a")

    def test_unsafe_path_and_duplicates_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "pillow-13.0.0-cp314-cp314-android_24_arm64_v8a.whl"
            wheel(archive, tag="cp314-cp314-android_24_arm64_v8a",
                  entry="PIL/../escape.so")
            with self.assertRaisesRegex(ValueError, "Unsafe wheel"):
                check_wheel(archive, "pillow", "arm64-v8a")
            archive.unlink()
            wheel(archive, tag="cp314-cp314-android_24_arm64_v8a",
                  entry="PIL/_imaging.so", duplicate=True)
            with self.assertRaisesRegex(ValueError, "Duplicate wheel"):
                check_wheel(archive, "pillow", "arm64-v8a")


if __name__ == "__main__":
    unittest.main(verbosity=2)
