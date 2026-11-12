#!/usr/bin/env python3
"""Contract tests for the dev-only FFBE Android in-process health probe."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).with_name("patch_bootstrap_probe.py")
spec = importlib.util.spec_from_file_location("bootstrap_probe", MODULE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def fixture(root: Path) -> str:
    (root / "apktool.yml").write_text("version: 3.0.3\n")
    transport = root / "smali_classes3/com/mene/exvius/LocalTransport.smali"
    transport.parent.mkdir(parents=True)
    transport.write_text(".class public Lcom/mene/exvius/LocalTransport;\n")
    original = (
        ".class public Lcom/square_enix/android_googleplay/FFBEWW/Lapis;\n"
        + probe.ON_CREATE + "\n    .locals 2\n"
        + probe.SUPER_CREATE + "\n    return-void\n.end method\n"
        + probe.ON_DESTROY + "\n    .locals 2\n"
        + probe.SUPER_DESTROY + "\n    return-void\n.end method\n"
    )
    lapis = root / probe.LAPIS
    lapis.parent.mkdir(parents=True)
    lapis.write_text(original)
    return original


class BootstrapProbeTests(unittest.TestCase):
    def test_injects_only_lifecycle_and_two_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = fixture(root)
            changed = probe.prepare(root)
            self.assertEqual(len(changed), 3)
            lapis = (root / probe.LAPIS).read_text()
            self.assertIn("->start()V", lapis)
            self.assertIn("->stop()V", lapis)
            self.assertEqual(lapis.count(probe.SUPER_CREATE), 1)
            self.assertEqual(lapis.count(probe.SUPER_DESTROY), 1)
            self.assertEqual(lapis.count("Lcom/mene/exvius/LocalBootstrap;"), 2)
            self.assertNotEqual(original, lapis)
            bootstrap = (root / probe.BOOTSTRAP_PATH).read_text()
            self.assertIn('const-string v0, "127.0.0.1"', bootstrap)
            self.assertIn('const/16 v2, 0x46a1', bootstrap)
            self.assertIn("Ljava/net/ServerSocket;-><init>(IILjava/net/InetAddress;)V", bootstrap)
            self.assertIn("FFBE-BOOTSTRAP-READY", bootstrap)
            self.assertNotIn("0.0.0.0", bootstrap)
            self.assertNotIn("VpnService", bootstrap)

    def test_second_patch_refused_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            probe.prepare(root)
            before = {p: (root / p).read_bytes() for p in
                      (probe.LAPIS, probe.BOOTSTRAP_PATH, probe.WORKER_PATH)}
            with self.assertRaisesRegex(ValueError, "already exists"):
                probe.prepare(root)
            after = {p: (root / p).read_bytes() for p in before}
            self.assertEqual(before, after)

    def test_unknown_hook_aborts_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            lapis = root / probe.LAPIS
            corrupted = lapis.read_text().replace(probe.SUPER_DESTROY, "    nop")
            lapis.write_text(corrupted)
            with self.assertRaisesRegex(ValueError, "Unknown|Unexpected"):
                probe.prepare(root)
            self.assertEqual(lapis.read_text(), corrupted)
            self.assertFalse((root / probe.BOOTSTRAP_PATH).exists())

    def test_transport_patch_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = fixture(root)
            (root / "smali_classes3/com/mene/exvius/LocalTransport.smali").unlink()
            with self.assertRaisesRegex(ValueError, "existing transport patch"):
                probe.prepare(root)
            self.assertEqual((root / probe.LAPIS).read_text(), original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
