#!/usr/bin/env python3
"""Non-destructive contract tests for the pinned FFBE 9.1.0 transport patch."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_FILE = Path(__file__).with_name("patch_transport.py")
spec = importlib.util.spec_from_file_location("network_patch", MODULE_FILE)
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)


def fixture(root: Path) -> None:
    (root / "apktool.yml").write_text("version: 3.0.3\n")
    for relative, signature, unused_register in patch.TARGETS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            ".class public Lexample/Test;\n"
            + signature
            + "\n    .locals 2\n    const/4 v0, 0x0\n    return-void\n.end method\n"
        )


class TransportPatchTests(unittest.TestCase):
    def test_four_call_sites_and_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            altered = patch.prepare(root, 18080)
            self.assertEqual(len(altered), 5)
            for relative, signature, register in patch.TARGETS:
                s = (root / relative).read_text()
                self.assertEqual(s.count("->rewrite(Ljava/lang/String;)Ljava/lang/String;"), 1)
                self.assertIn(f"move-result-object {register}", s)
            helper = (root / patch.HELPER).read_text()
            self.assertIn("http://127.0.0.1:18080", helper)
            for hostname in ("gumi.sg", ".gumi.sg", "exvius.com", ".exvius.com"):
                self.assertIn(f'const-string v2, "{hostname}"', helper)
            self.assertIn('Ljava/net/URL;->getFile()', helper)
            self.assertNotIn("javax/net/ssl", helper)

    def test_rejects_second_patch_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            patch.prepare(root, 18080)
            previous = {(root / name).read_bytes() for name, *_ in patch.TARGETS}
            with self.assertRaisesRegex(ValueError, "Already patched"):
                patch.prepare(root, 18080)
            current = {(root / name).read_bytes() for name, *_ in patch.TARGETS}
            self.assertEqual(previous, current)

    def test_unknown_layout_aborts_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            relative, *_ = patch.TARGETS[-1]
            target = root / relative
            target.write_text("not a recognized DEX layout\n")
            previous = {(root / name).read_bytes() for name, *_ in patch.TARGETS}
            with self.assertRaisesRegex(ValueError, "Expected one matching method"):
                patch.prepare(root)
            self.assertEqual(previous, {(root / name).read_bytes() for name, *_ in patch.TARGETS})
            self.assertFalse((root / patch.HELPER).exists())

    def test_rejects_privileged_and_invalid_ports(self):
        for port in (0, 1, 80, 443, 1023, 65536, -1):
            with self.assertRaises(ValueError):
                patch.network_helper(port)


if __name__ == "__main__":
    unittest.main(verbosity=2)
