"""Lab-only patched Android downloader: URL isolation and byte-for-byte APK diff."""
from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from build_local_install_lab import (
    LOCAL_ASSETS, LOCAL_LATEST, SOURCE_ASSETS, SOURCE_LATEST,
    patch_updates, replace_installer_only, use_resumable_for_manifest,
)


class LabDownloaderTests(unittest.TestCase):
    def test_url_rewrite_is_exact_and_double_patch_blocked(self):
        source = ("const-string '" + SOURCE_LATEST + "'\n") * 3
        source += ("const-string '" + SOURCE_ASSETS + "'\n") * 3
        source += (".method private static download(Landroid/content/Context;"
                   "Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;JJZ"
                   "Ljava/lang/String;)Ljava/io/File;\n"
                   "    if-nez p8, :cond_2\n"
                   "    invoke-static/range {v1 .. v9}, "
                   "Lcom/exvius/local/DataUpdates;->resumableDownload(...)Ljava/io/File;\n"
                   "    invoke-static/range {p0 .. p8}, "
                   "Lcom/exvius/local/DataUpdates;->downloadManager(...)Ljava/io/File;\n"
                   ".end method\n")
        patched = patch_updates(source)
        self.assertIn("    nop", patched)
        self.assertNotIn("if-nez p8, :cond_2", patched)
        self.assertEqual(patched.count(LOCAL_LATEST), 3)
        self.assertEqual(patched.count(LOCAL_ASSETS), 3)
        self.assertNotIn(SOURCE_LATEST, patched)
        self.assertNotIn(SOURCE_ASSETS, patched)
        with self.assertRaisesRegex(ValueError, "Unrecognized"):
            patch_updates(patched)
        with self.assertRaisesRegex(ValueError, "Unrecognized"):
            patch_updates(source.replace(SOURCE_ASSETS, "other", 1))

    def test_only_fourth_dex_is_modified(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / "source.apk"
            compiled = Path(temp) / "rebuilt.apk"
            output = Path(temp) / "local-lab.apk"
            with zipfile.ZipFile(base, "w") as archive:
                archive.writestr("AndroidManifest.xml", b"binary-xml")
                for n in range(1, 5):
                    name = f"classes{n}.dex" if n != 1 else "classes.dex"
                    archive.writestr(name, b"dex\noriginal" + str(n).encode())
                archive.writestr("lib/arm64-v8a/libgame.so", b"original game library")
            with zipfile.ZipFile(compiled, "w") as archive:
                archive.writestr("classes4.dex", b"dex\n" + LOCAL_LATEST.encode()
                                 + b"\n" + LOCAL_ASSETS.encode())
            replace_installer_only(base, compiled, output)
            with zipfile.ZipFile(base) as old, zipfile.ZipFile(output) as new:
                self.assertEqual(old.namelist(), new.namelist())
                for name in old.namelist():
                    if name != "classes4.dex":
                        self.assertEqual(old.read(name), new.read(name))
            with self.assertRaises(FileExistsError):
                replace_installer_only(base, compiled, output)


if __name__ == "__main__":
    unittest.main()
