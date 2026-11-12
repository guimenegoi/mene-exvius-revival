#!/usr/bin/env python3
"""Source-only tests for the signed, import-only Revival engine bundle."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import embedded_engine
import package_engine_probe


def make_archive(path: Path, files: dict[str, bytes]) -> None:
    manifest = {
        "format": 1,
        "files": {
            name: {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
            for name, data in files.items()
        },
    }
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(embedded_engine.MANIFEST, json.dumps(manifest))
        for name, value in files.items():
            zf.writestr(embedded_engine.ROOT + name, value,
                        compress_type=zipfile.ZIP_STORED)


class EngineBundleTests(unittest.TestCase):
    def test_validate_engine_paths(self):
        for name in (
            "/etc/passwd", "source/server/../../outside.py",
            "ios-server/../outside.py", "vendor/yaml/x\\y.py",
            "other/unknown.py",
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                embedded_engine.validate_relative(name)
        self.assertEqual(
            embedded_engine.validate_relative("source/server/capture_server.py").as_posix(),
            "source/server/capture_server.py",
        )

    def test_extract_verify_and_incremental_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / "stdlib.zip"
            contents = {
                "ios-server/serve.py": b"print('fake serve')\n",
                "source/server/capture_server.py": b"class Handler: pass\n",
                "vendor/yaml/__init__.py": b"def safe_load(text): return {'enabled': True}\n",
            }
            make_archive(bundle, contents)
            destination = root / "engine"
            self.assertEqual(embedded_engine.install(bundle, destination), len(contents))
            self.assertEqual(embedded_engine.install(bundle, destination), 0)
            file = destination / "ios-server/serve.py"
            file.write_bytes(b"tampered")
            self.assertEqual(embedded_engine.install(bundle, destination), 1)
            self.assertEqual(file.read_bytes(), contents["ios-server/serve.py"])

    def test_rejects_manifest_path_traversal_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = root / "bad.zip"
            make_archive(zip_path, {"source/server/../../escape.py": b"oops"})
            with self.assertRaises(ValueError):
                embedded_engine.install(zip_path, root / "engine")
            self.assertFalse((root / "escape.py").exists())

    def test_rejects_preexisting_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "stdlib.zip"
            make_archive(archive, {"source/server/capture_server.py": b"source"})
            (root / "engine").symlink_to(root / "outside", target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                embedded_engine.install(archive, root / "engine")

    def test_builder_adds_only_tracked_source_and_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stdlib = root / "stdlib.zip"
            with zipfile.ZipFile(stdlib, "w") as zf:
                zf.writestr("encodings/__init__.py", b"")
                zf.writestr("json/__init__.py", b"")
            path = root / "result.zip"
            source = {
                "ios-server/serve.py": b"def configure_engine(): pass\n",
                "ios-server/certs.py": b"x=1\n",
                "source/server/capture_server.py": b"class Handler: pass\n",
            }
            with patch.object(package_engine_probe, "git_tracked_engine",
                              return_value=source), patch.object(
                package_engine_probe, "pure_yaml",
                return_value={"vendor/yaml/__init__.py": b"fake yaml\n",
                              "vendor/LICENSE-pyyaml.txt": b"MIT\n"},
            ):
                counts = package_engine_probe.package_engine(
                    root, root / "fake.tar.gz", stdlib, path,
                )
            self.assertEqual(counts["engine_files"], 5)
            with zipfile.ZipFile(path) as zf:
                self.assertIn("ffbe_engine_bootstrap.py", zf.namelist())
                self.assertIn("ffbe_engine/source/server/capture_server.py", zf.namelist())
                self.assertEqual(zf.testzip(), None)
            self.assertEqual(
                embedded_engine.install(path, root / "engine"),
                5,
            )

    def test_pillow_cp314_wheel_uses_existing_engine_bundle(self):
        from test_python_probe import fake_elf
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wheel = root / "pillow-13.0.0-cp314-cp314-android_24_arm64_v8a.whl"
            with zipfile.ZipFile(wheel, "w") as zf:
                zf.writestr("pillow-13.0.0.dist-info/WHEEL",
                            "Wheel-Version: 1.0\nTag: cp314-cp314-android_24_arm64_v8a\n")
                zf.writestr("pillow-13.0.0.dist-info/licenses/LICENSE", b"License")
                zf.writestr("PIL/__init__.py", b"")
                zf.writestr("PIL/Image.py", b"")
                zf.writestr("PIL/_imaging.cpython-314-aarch64-linux-android.so",
                            fake_elf(183))
            bundled = package_engine_probe.native_pillow(wheel, "arm64-v8a")
            self.assertEqual(len(bundled), 4)
            self.assertEqual(bundled["vendor/LICENSE-pillow.txt"], b"License")
            archive = root / "stdlib.zip"
            make_archive(archive, bundled)
            target = root / "engine"
            self.assertEqual(embedded_engine.install(archive, target), len(bundled))
            self.assertEqual(embedded_engine.install(archive, target), 0)
            so = target / "vendor/PIL/_imaging.cpython-314-aarch64-linux-android.so"
            self.assertEqual(so.stat().st_mode & 0o777, 0o400)
            with self.assertRaisesRegex(ValueError, "Android wheel tag"):
                package_engine_probe.native_pillow(wheel, "x86_64")

    def test_android_crypto_and_cffi_wheels_are_validated(self):
        from test_python_probe import fake_elf
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            crypto = root / "cryptography-50.0.2-cp314-abi3-android_24_arm64_v8a.whl"
            with zipfile.ZipFile(crypto, "w") as zf:
                zf.writestr("cryptography-50.0.2.dist-info/WHEEL",
                            "Wheel-Version: 1.0\nTag: cp314-abi3-android_24_arm64_v8a\n")
                zf.writestr("cryptography/__init__.py", b"")
                zf.writestr("cryptography/hazmat/bindings/_rust.abi3.so",
                            fake_elf(183))
                for name in ("LICENSE", "LICENSE.APACHE", "LICENSE.BSD"):
                    zf.writestr("cryptography-50.0.2.dist-info/licenses/" + name,
                                b"copyright")
            result = package_engine_probe.native_cryptography(crypto, "arm64-v8a")
            self.assertEqual(len(result), 5)
            with self.assertRaisesRegex(ValueError, "Android wheel tag"):
                package_engine_probe.native_cryptography(crypto, "x86_64")

            cffi = root / "cffi-2.1.1-cp314-cp314-android_24_arm64_v8a.whl"
            with zipfile.ZipFile(cffi, "w") as zf:
                zf.writestr("cffi-2.1.1.dist-info/WHEEL",
                            "Wheel-Version: 1.0\nTag: cp314-cp314-android_24_arm64_v8a\n")
                zf.writestr("cffi/__init__.py", b"")
                zf.writestr("_cffi_backend.cpython-314-aarch64-linux-android.so",
                            fake_elf(183))
                zf.writestr("cffi-2.1.1.dist-info/licenses/LICENSE", b"copyright")
            bundled = package_engine_probe.native_cffi(cffi, "arm64-v8a")
            self.assertEqual(len(bundled), 3)
            self.assertTrue(all(embedded_engine.validate_relative(k) for k in bundled))
            archive = root / "stdlib.zip"
            make_archive(archive, {**result, **bundled})
            engine = root / "engine"
            self.assertEqual(embedded_engine.install(archive, engine), 8)
            self.assertEqual(embedded_engine.install(archive, engine), 0)
            rust = engine / "vendor/cryptography/hazmat/bindings/_rust.abi3.so"
            self.assertEqual(rust.stat().st_mode & 0o777, 0o400)

    def test_crypto_requires_complete_cffi_dependency_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(package_engine_probe, "git_tracked_engine",
                              return_value={"ios-server/serve.py": b"stub"}), \
                 patch.object(package_engine_probe, "pure_yaml",
                              return_value={"vendor/yaml/__init__.py": b"stub"}):
                with self.assertRaisesRegex(ValueError, "requires CFFI"):
                    package_engine_probe.package_engine(
                        root, root / "fake.tar.gz", root / "stdlib.zip",
                        root / "out.zip", crypto_wheel=root / "crypto.whl",
                    )
            self.assertFalse((root / "out.zip").exists())

    def test_pinned_pycparser_and_libffi_reject_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / "pycparser-3.12-py3-none-any.whl"
            p.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                package_engine_probe.pure_pycparser(p)
            lib = root / "libffi-3.5.2.tar.gz"
            lib.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                package_engine_probe.libffi_license(lib)

    def test_py_yaml_hash_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pyyaml-6.0.3.tar.gz"
            path.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                package_engine_probe.pure_yaml(path)

    def test_tzdata_hash_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tzdata-2026.6-py2.py3-none-any.whl"
            path.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                package_engine_probe.pure_tzdata(path)

    def test_tzdata_universal_wheel_includes_zone_and_licenses(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tzdata-2026.6-py2.py3-none-any.whl"
            with zipfile.ZipFile(path, "w") as zf:
                for file, value in {
                    "tzdata/__init__.py": b"__version__='2026.6'\n",
                    "tzdata/zoneinfo/__init__.py": b"",
                    "tzdata/zoneinfo/America/Sao_Paulo": b"TZif2",
                    "tzdata-2026.6.dist-info/licenses/LICENSE": b"License\n",
                    "tzdata-2026.6.dist-info/licenses/licenses/LICENSE_APACHE":
                        b"Apache license\n",
                }.items():
                    zf.writestr(file, value)
            with patch.object(
                package_engine_probe, "TZDATA_SHA256",
                hashlib.sha256(path.read_bytes()).hexdigest()
            ):
                result = package_engine_probe.pure_tzdata(path)
            self.assertEqual(result["vendor/tzdata/zoneinfo/America/Sao_Paulo"], b"TZif2")
            self.assertEqual(result["vendor/LICENSE-tzdata.txt"], b"License\n")
            self.assertIn("vendor/LICENSE-tzdata-apache.txt", result)
            self.assertEqual(len(result), 5)

    def test_tzdata_rejects_traversal_in_wheel(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tzdata-2026.6-py2.py3-none-any.whl"
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("tzdata/../../../outside", b"escaped")
            with patch.object(
                package_engine_probe, "TZDATA_SHA256",
                hashlib.sha256(path.read_bytes()).hexdigest()
            ), self.assertRaises(ValueError):
                package_engine_probe.pure_tzdata(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
