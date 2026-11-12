#!/usr/bin/env python3
"""Contract tests: Python stdlib asset and in-process execution hook."""
import tempfile
import unittest
import zipfile
from pathlib import Path

import package_stdlib_probe as bundle
import patch_python_execute as execute
import patch_python_probe as version
from patch_bootstrap_probe import SUPER_CREATE, LAPIS
from test_python_probe import decoded_fixture


def fixture(root: Path) -> None:
    decoded_fixture(root)
    lapis = root / LAPIS
    lapis.parent.mkdir(parents=True, exist_ok=True)
    lapis.write_text(
        ".class public Lcom/square_enix/android_googleplay/FFBEWW/Lapis;\n"
        ".method protected onCreate(Landroid/os/Bundle;)V\n"
        "    .locals 2\n"
        "    invoke-static {}, Lcom/mene/exvius/LocalBootstrap;->start()V\n"
        + SUPER_CREATE
        + "\n    return-void\n.end method\n"
    )
    version.prepare(root)


class EmbeddedExecuteTests(unittest.TestCase):
    def test_hook_runs_after_superclass_with_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            files = execute.prepare(root)
            self.assertEqual(len(files), 2)
            lapis = (root / LAPIS).read_text()
            self.assertLess(lapis.index(SUPER_CREATE), lapis.index("->runDemo("))
            self.assertIn("invoke-static {p0}", lapis)
            helper = (root / execute.PROBE_PATH).read_text()
            self.assertIn(" native execute(Landroid/content/Context;)", helper)
            self.assertIn(".catch Ljava/lang/Throwable;", helper)
            for library in ("crypto_python", "ssl_python", "sqlite3_python"):
                self.assertIn(f'const-string v2, "{library}"', helper)

    def test_double_patch_refused_before_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            execute.prepare(root)
            before = {name: (root / name).read_bytes() for name in
                      (LAPIS, execute.PROBE_PATH)}
            with self.assertRaisesRegex(ValueError, "Already patched"):
                execute.prepare(root)
            self.assertEqual(before, {name: (root / name).read_bytes() for name in before})

    def test_unknown_lifecycle_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            lapis = root / LAPIS
            lapis.write_text(lapis.read_text().replace(SUPER_CREATE, "    nop"))
            original = lapis.read_bytes()
            with self.assertRaisesRegex(ValueError, "bootstrap missing"):
                execute.prepare(root)
            self.assertEqual(original, lapis.read_bytes())

    def test_bundle_contains_real_python_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prefix = root / "prefix/lib/python3.14"
            for relative in ("encodings/__init__.py", "json/__init__.py", "os.py"):
                f = prefix / relative
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text("# tiny demo\n")
            output = root / "stdlib.zip"
            bundle.pack_stdlib(root / "prefix", output)
            with zipfile.ZipFile(output) as zf:
                self.assertEqual(set(zf.namelist()),
                                 {"encodings/__init__.py", "json/__init__.py", "os.py"})
                self.assertEqual(zf.read("os.py"), b"# tiny demo\n")
                self.assertTrue(all(info.compress_type == zipfile.ZIP_STORED
                                    for info in zf.infolist()))

    def test_base_preservation_exactly_two_dex_and_one_new_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "orig.apk"
            dex = root / "dex.apk"
            final = root / "final.apk"
            library = root / "stdlib.zip"
            library.write_bytes(b"stdlib demo")
            names = ["AndroidManifest.xml", "classes.dex", "classes3.dex"]
            for file, changed in ((original, False), (dex, True)):
                with zipfile.ZipFile(file, "w") as zf:
                    for name in names:
                        value = (b"new" if changed and name.endswith(".dex") else b"orig")
                        zf.writestr(name, value)
            bundle.embed_asset(original, dex, final, library)
            with zipfile.ZipFile(final) as zf:
                self.assertEqual(zf.namelist(), names + [bundle.ASSET_NAME])
                self.assertEqual(zf.read("AndroidManifest.xml"), b"orig")
                self.assertEqual(zf.read(bundle.ASSET_NAME), b"stdlib demo")
            with self.assertRaises(FileExistsError):
                bundle.embed_asset(original, dex, final, library)

    def test_base_with_unexpected_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original, bad, out, library = [root / name for name in
                                            ("original.apk", "bad.apk", "out.apk", "stdlib.zip")]
            library.write_bytes(b"demo")
            for path, suffix in ((original, b"old"), (bad, b"new")):
                with zipfile.ZipFile(path, "w") as zf:
                    for name in ("AndroidManifest.xml", "classes.dex", "classes3.dex"):
                        zf.writestr(name, suffix)
            with self.assertRaisesRegex(ValueError, "unexpected changes"):
                bundle.embed_asset(original, bad, out, library)
            self.assertFalse(out.exists())


    def test_official_native_assets_manifest_and_elf(self):
        from test_python_probe import fake_elf
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp)
            folder = prefix / "lib/python3.14/lib-dynload"
            folder.mkdir(parents=True)
            (folder / "_ssl.cpython-314-aarch64-linux-android.so").write_bytes(fake_elf(183))
            (folder / "zlib.cpython-314-aarch64-linux-android.so").write_bytes(fake_elf(183))
            assets = bundle.native_assets(prefix, "arm64-v8a")
            self.assertEqual(len(assets), 3)
            self.assertIn(b"_ssl.cpython-314-aarch64-linux-android.so\n",
                          assets[bundle.NATIVE_INDEX])
            self.assertIn(b"zlib.cpython-314-aarch64-linux-android.so\n",
                          assets[bundle.NATIVE_INDEX])
            self.assertTrue(all(key.startswith("assets/ffbe_python/") for key in assets))
            (folder / "zlib.cpython-314-aarch64-linux-android.so").write_bytes(fake_elf(62))
            with self.assertRaisesRegex(ValueError, "ELF machine"):
                bundle.native_assets(prefix, "arm64-v8a")

    def test_native_asset_name_guard(self):
        from test_python_probe import fake_elf
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp)
            folder = prefix / "lib/python3.14/lib-dynload"
            folder.mkdir(parents=True)
            (folder / "_ssl.cpython-314-aarch64-linux-android.so").write_bytes(fake_elf(183))
            (folder / "unsafe+module.so").write_bytes(fake_elf(183))
            with self.assertRaisesRegex(ValueError, "Unsafe native module basename"):
                bundle.native_assets(prefix, "arm64-v8a")

if __name__ == "__main__":
    unittest.main(verbosity=2)
