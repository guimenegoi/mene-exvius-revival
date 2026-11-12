"""First-run manifest and APK graft verification (no original binaries needed)."""
from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from patch_first_run import (ANDROID, INSTALLER, MAIN, ACTION_MAIN, LAUNCHER,
                             UPSTREAM_LATEST, UPSTREAM_PINNED,
                             merge_apk, patch_manifest, pin_manifest_url)

SYNTHETIC = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
          package="com.square_enix.android_googleplay.FFBEWW">
  <uses-permission android:name="android.permission.INTERNET"/>
  <application android:name="com.example.GameApplication">
    <activity android:name="com.square_enix.android_googleplay.FFBEWW.Lapis"
              android:exported="true">
      <intent-filter>
        <action android:name="android.intent.action.MAIN"/>
        <category android:name="android.intent.category.LAUNCHER"/>
      </intent-filter>
      <intent-filter>
        <action android:name="android.intent.action.VIEW"/>
        <category android:name="android.intent.category.DEFAULT"/>
      </intent-filter>
    </activity>
    <activity android:name="com.example.Secondary"/>
  </application>
</manifest>
"""


class FirstRunPatchTests(unittest.TestCase):
    def parse(self, content):
        return ET.fromstring(content)

    def test_launcher_only_moves_and_preserves_deep_link(self):
        root = self.parse(patch_manifest(SYNTHETIC.encode()))
        app = root.find("application")
        self.assertEqual(app.get(ANDROID + "name"), "com.example.GameApplication")
        self.assertEqual(root.find("uses-permission").get(ANDROID + "name"),
                         "android.permission.INTERNET")
        activities = {a.get(ANDROID + "name"): a for a in app.findall("activity")}
        self.assertEqual(len(activities), 3)
        self.assertEqual(len(activities[MAIN].findall("intent-filter")), 1)
        self.assertEqual(activities[MAIN].find("intent-filter/action").get(
            ANDROID + "name"), "android.intent.action.VIEW")
        installer = activities[INSTALLER]
        self.assertEqual(installer.get(ANDROID + "exported"), "true")
        self.assertEqual(installer.get(ANDROID + "screenOrientation"), "portrait")
        self.assertEqual(installer.get(ANDROID + "theme"),
                         "@android:style/Theme.Material.NoActionBar")
        self.assertEqual(installer.find("intent-filter/action").get(
            ANDROID + "name"), ACTION_MAIN)
        self.assertEqual(installer.find("intent-filter/category").get(
            ANDROID + "name"), LAUNCHER)

    def test_pinned_upstream_manifest_is_required(self):
        source = "field " + UPSTREAM_LATEST + "\n" + (
            "  const-string " + UPSTREAM_LATEST + "\n") * 2
        pinned = pin_manifest_url(source)
        self.assertEqual(pinned.count(UPSTREAM_PINNED), 3)
        self.assertNotIn(UPSTREAM_LATEST, pinned)
        for changed in (source.replace(UPSTREAM_LATEST, "bad", 1), pinned):
            with self.assertRaisesRegex(ValueError, "Unrecognized"):
                pin_manifest_url(changed)

    def test_second_patch_rejected(self):
        edited = patch_manifest(SYNTHETIC.encode())
        with self.assertRaisesRegex(ValueError, "already present"):
            patch_manifest(edited)

    def test_unknown_package_and_duplicate_launcher_rejected(self):
        with self.assertRaisesRegex(ValueError, "pinned"):
            patch_manifest(SYNTHETIC.replace(
                "com.square_enix.android_googleplay.FFBEWW",
                "com.example.different").encode())
        another = SYNTHETIC.replace(
            '<activity android:name="com.example.Secondary"/>',
            '<activity android:name="com.example.Secondary">'
            '<intent-filter><action android:name="android.intent.action.MAIN"/>'
            '<category android:name="android.intent.category.LAUNCHER"/>'
            '</intent-filter></activity>'
        )
        with self.assertRaisesRegex(ValueError, "exactly one"):
            patch_manifest(another.encode())

    def test_apk_merge_preserves_every_unchanged_member(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base, out = root / "base.apk", root / "new.apk"
            original = {
                "AndroidManifest.xml": b"\x03\x00\x08\x00original",
                "classes.dex": b"dex\nfake1",
                "classes2.dex": b"dex\nfake2",
                "classes3.dex": b"dex\nfake3",
                "resources.arsc": b"resources untouched",
                "assets/sample.zip": b"assets untouched",
            }
            with zipfile.ZipFile(base, "w") as z:
                for name, value in original.items():
                    z.writestr(name, value)
            compiled = b"\x03\x00\x08\x00updated"
            new_dex = b"dex\n036\x00upstream first-run activity"
            result = merge_apk(base, compiled, new_dex, out)
            self.assertEqual(result, {
                "preserved_members": len(original) - 1,
                "new_dex_bytes": len(new_dex),
            })
            with zipfile.ZipFile(out) as z:
                self.assertEqual(len(z.namelist()), len(original) + 1)
                for name, before in original.items():
                    expected = compiled if name == "AndroidManifest.xml" else before
                    self.assertEqual(z.read(name), expected)
                self.assertEqual(z.read("classes4.dex"), new_dex)
            with self.assertRaises(FileExistsError):
                merge_apk(base, compiled, new_dex, out)

    def test_existing_fourth_dex_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "input.apk"
            with zipfile.ZipFile(src, "w") as z:
                for name in ("AndroidManifest.xml", "classes.dex",
                             "classes2.dex", "classes3.dex", "classes4.dex"):
                    z.writestr(name, b"test")
            with self.assertRaisesRegex(ValueError, "already"):
                merge_apk(src, b"\x03\x00\x08\x00", b"dex\n", root / "output.apk")


if __name__ == "__main__":
    unittest.main()
