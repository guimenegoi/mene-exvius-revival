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

    def test_py_yaml_hash_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pyyaml-6.0.3.tar.gz"
            path.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                package_engine_probe.pure_yaml(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
