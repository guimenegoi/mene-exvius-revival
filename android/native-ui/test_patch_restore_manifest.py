"""Text-only Android manifest contract; synthetic fixtures, no APK touched."""
import unittest
import xml.etree.ElementTree as ET

from patch_restore_manifest import (
    patch_manifest, ANDROID, PACKAGE, ACTIVITY, MAIN, LAUNCHER,
)

XML = b"""<manifest xmlns:android="http://schemas.android.com/apk/res/android"
 package="com.square_enix.android_googleplay.FFBEWW">
 <uses-permission android:name="android.permission.INTERNET"/>
 <application>
  <activity android:name="com.square_enix.android_googleplay.FFBEWW.Lapis"
    android:exported="true">
   <intent-filter><action android:name="android.intent.action.MAIN"/>
    <category android:name="android.intent.category.LAUNCHER"/>
   </intent-filter>
  </activity>
 </application>
</manifest>"""


class ManifestTests(unittest.TestCase):
    def test_lab_activity_has_separate_launcher_and_no_new_permission(self):
        root = ET.fromstring(patch_manifest(XML))
        app = root.find("application")
        activities = app.findall("activity")
        self.assertEqual(len(activities), 2)
        self.assertEqual(activities[0].get(ANDROID + "name"),
                         "com.square_enix.android_googleplay.FFBEWW.Lapis")
        self.assertEqual(activities[1].get(ANDROID + "name"), ACTIVITY)
        self.assertEqual(activities[1].get(ANDROID + "exported"), "true")
        self.assertIn("LAB", activities[1].get(ANDROID + "label"))
        self.assertEqual(len(root.findall("uses-permission")), 1)
        launcher = activities[1].find("intent-filter")
        self.assertEqual(launcher.find("action").get(ANDROID + "name"), MAIN)
        self.assertEqual(launcher.find("category").get(ANDROID + "name"), LAUNCHER)

    def test_rejects_repatch(self):
        with self.assertRaisesRegex(ValueError, "already registered"):
            patch_manifest(patch_manifest(XML))

    def test_rejects_wrong_package(self):
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            patch_manifest(XML.replace(PACKAGE.encode(), b"other.package"))

    def test_rejects_missing_launcher(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            patch_manifest(XML.replace(LAUNCHER.encode(), b"not.a.launcher"))


if __name__ == "__main__":
    unittest.main()
