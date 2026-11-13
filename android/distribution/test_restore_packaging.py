"""Synthetic APK repacker contract for the opt-in restore bootstrap.

Creates tiny ZIP fixtures: no original APK, no save, no Android device.
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import repack_next_rc as repack


REPO = Path(__file__).resolve().parents[2]
SOURCE = {"source/server/offline_menu.py": b"def test_only():\n    return True\n"}


def fake_base(destination: Path):
    inner_file = io.BytesIO()
    with zipfile.ZipFile(inner_file, "w") as nested:
        for name, data in (
            ("ffbe_offline_manifest.json", (REPO / "data/latest.json").read_bytes()),
            ("ffbe_engine_manifest.json", b'{"files":{}}'),
        ):
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_STORED
            nested.writestr(info, data)
    with zipfile.ZipFile(destination, "w") as apk:
        apk.writestr(repack.ASSET, inner_file.getvalue())
        apk.writestr("AndroidManifest.xml", b"synthetic fixture")


class RestorePackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.base = self.dir / "base.apk"
        fake_base(self.base)

    def test_restore_cannot_be_packaged_without_backup_dependencies(self):
        out = self.dir / "invalid.apk"
        with patch.object(repack, "tracked_sources", return_value=SOURCE):
            with self.assertRaisesRegex(ValueError, "requires the optional backup"):
                repack.build(REPO, self.base, out, with_restore=True)
        self.assertFalse(out.exists())

    def test_stable_mode_contains_no_restore_module(self):
        out = self.dir / "stable.apk"
        with patch.object(repack, "tracked_sources", return_value=SOURCE):
            report = repack.build(REPO, self.base, out)
        self.assertFalse(report["restore_experimental"])
        self.assertFalse(report["backup_experimental"])
        with zipfile.ZipFile(out) as apk, zipfile.ZipFile(
                apk.open(repack.ASSET)) as inner:
            self.assertNotIn("ffbe_restore_startup.py", inner.namelist())
            self.assertNotIn("ffbe_save_restore.py", inner.namelist())
            self.assertNotIn("ffbe_backup_transport.py", inner.namelist())
            self.assertIn("ffbe_local_http.py", inner.namelist())
        self.assertEqual(zipfile.ZipFile(self.base).read("AndroidManifest.xml"),
                         b"synthetic fixture")

    def test_restore_mode_embeds_dependencies_as_stored_modules(self):
        out = self.dir / "restore.apk"
        with patch.object(repack, "tracked_sources", return_value=SOURCE):
            report = repack.build(
                REPO, self.base, out, with_backup=True, with_restore=True)
        self.assertTrue(report["restore_experimental"])
        self.assertTrue(report["backup_experimental"])
        self.assertFalse(report["signed"])
        with zipfile.ZipFile(out) as apk, zipfile.ZipFile(
                apk.open(repack.ASSET)) as inner:
            for name, path in (
                ("ffbe_restore_startup.py", REPO / "android/runtime/restore_startup.py"),
                ("ffbe_save_restore.py", REPO / "android/backup/save_restore.py"),
                ("ffbe_backup_transport.py", REPO / "android/backup/lxc_backup.py"),
                ("ffbe_backup.py", REPO / "android/backup/embedded_client.py"),
            ):
                member = inner.getinfo(name)
                self.assertEqual(member.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(inner.read(name), path.read_bytes())
            self.assertIn("ffbe_local_http.py", inner.namelist())
            self.assertEqual(apk.read("AndroidManifest.xml"), b"synthetic fixture")


if __name__ == "__main__":
    unittest.main()
