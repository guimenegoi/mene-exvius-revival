#!/usr/bin/env python3
"""Contract tests for the dev-only native Python load probe."""
import tempfile
import unittest
import zipfile
from pathlib import Path

import build_python_probe as build
import patch_python_probe as patch


def decoded_fixture(root: Path) -> str:
    (root / "apktool.yml").write_text("version: 3.0.3\n")
    transport = root / "smali_classes3/com/mene/exvius/LocalTransport.smali"
    transport.parent.mkdir(parents=True)
    transport.write_text(".class public Lcom/mene/exvius/LocalTransport;\n")
    bootstrap = root / patch.BOOTSTRAP_PATH
    bootstrap.write_text(
        ".class public Lcom/mene/exvius/LocalBootstrap;\n"
        ".method public static start()V\n"
        "    .locals 3\n"
        "    const-string v0, \"FFBE-Local-Probe\"\n"
        "    return-void\n.end method\n"
    )
    return bootstrap.read_text()


def fake_elf(machine: int) -> bytes:
    return b"\x7fELF\x02\x01" + b"\x00" * 12 + machine.to_bytes(2, "little") + b"demo"


class NativePythonProbeTests(unittest.TestCase):
    def test_existing_bootstrap_is_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous = decoded_fixture(root)
            paths = patch.prepare(root)
            self.assertEqual(len(paths), 2)
            self.assertIn(
                "Lcom/mene/exvius/LocalPythonProbe;->probe()V",
                (root / patch.BOOTSTRAP_PATH).read_text(),
            )
            self.assertIn(previous.split("    const-string")[1].split("\n")[0],
                          (root / patch.BOOTSTRAP_PATH).read_text())
            helper = (root / patch.PROBE_PATH).read_text()
            self.assertIn("python3.14", helper)
            self.assertIn("ffbe_python_probe", helper)
            self.assertIn("FFBE-EmbeddedPython", helper)
            self.assertIn("Ljava/lang/Throwable;", helper)
            self.assertNotIn("Py_Initialize", helper)

    def test_reject_double_patch_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            decoded_fixture(root)
            patch.prepare(root)
            before = (root / patch.BOOTSTRAP_PATH).read_bytes()
            with self.assertRaisesRegex(ValueError, "already exists"):
                patch.prepare(root)
            self.assertEqual(before, (root / patch.BOOTSTRAP_PATH).read_bytes())

    def test_unknown_bootstrap_refused_without_side_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            decoded_fixture(root)
            path = root / patch.BOOTSTRAP_PATH
            path.write_text(path.read_text().replace(".locals 3", ".locals 2"))
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "Unknown"):
                patch.prepare(root)
            self.assertEqual(before, path.read_bytes())
            self.assertFalse((root / patch.PROBE_PATH).exists())

    def test_requires_original_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = decoded_fixture(root)
            (root / "smali_classes3/com/mene/exvius/LocalTransport.smali").unlink()
            with self.assertRaisesRegex(ValueError, "existing transport"):
                patch.prepare(root)
            self.assertEqual(original, (root / patch.BOOTSTRAP_PATH).read_text())

    def test_split_injection_preserves_existing_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "split.apk"
            output = root / "modified.apk"
            native = root / build.SO
            libpy = root / build.LIBPYTHON
            native.write_bytes(fake_elf(183))
            libpy.write_bytes(fake_elf(183))
            with zipfile.ZipFile(original, "w") as zf:
                zf.writestr("AndroidManifest.xml", b"original manifest")
                zf.writestr("lib/arm64-v8a/libgame.so", b"original game")
            original_hash = build.digest(original)
            build.embed_split(original, output, "arm64-v8a", native, libpy)
            self.assertEqual(original_hash, build.digest(original))
            with zipfile.ZipFile(output) as zf:
                self.assertEqual(zf.read("AndroidManifest.xml"), b"original manifest")
                self.assertEqual(zf.read("lib/arm64-v8a/libgame.so"), b"original game")
                self.assertEqual(zf.read("lib/arm64-v8a/" + build.SO), native.read_bytes())
                self.assertEqual(zf.read("lib/arm64-v8a/" + build.LIBPYTHON), libpy.read_bytes())
            with self.assertRaises(FileExistsError):
                build.embed_split(original, output, "arm64-v8a", native, libpy)

    def test_mismatched_abi_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "example.so"
            p.write_bytes(fake_elf(62))
            with self.assertRaisesRegex(ValueError, "Unexpected ELF machine"):
                build.verify_elf(p, "arm64-v8a")

    def test_archive_hash_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "python-3.14.10-aarch64-linux-android.tar.gz"
            p.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                build.verify_archive(p, "arm64-v8a")


if __name__ == "__main__":
    unittest.main(verbosity=2)
