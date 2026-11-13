"""Native Android first-run profile uses shipped resource versions, not iPhone patches."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "source/server"))
sys.path.insert(0, str(ROOT / "ios-server"))

import ffbe_battle  # noqa: E402
import ios_tables  # noqa: E402

# Do not pollute sys.modules["serve"]: local_http.run() expressly rejects a
# server imported before its private FFBE_DATA_DIR is bound.
spec = importlib.util.spec_from_file_location(
    "ffbe_native_android_test_serve", ROOT / "ios-server/serve.py"
)
serve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serve)


class NativeAndroidProfileTests(unittest.TestCase):
    def test_android_receives_shipped_mst_versions_without_ios_bumps(self):
        input_reply = {
            "c1qYg84Q": [
                {"a4hXTIm0": "F_APP_VERSION_AND", "wM9AfX6I": "1167"},
                {"a4hXTIm0": "F_MST_VERSION", "wM9AfX6I": "0"},
                {"a4hXTIm0": "F_TEXT_TEXT_EN", "wM9AfX6I": "219000"},
                {"a4hXTIm0": "F_MISSION_MST", "wM9AfX6I": "201527"},
                {"a4hXTIm0": "F_NEVER_SHIPPED", "wM9AfX6I": "1000"},
            ],
            "other": [1, 2, 3],
        }
        shipped = {
            "F_TEXT_TEXT_EN": "263", "F_MISSION_MST": "527",
            "F_RESOURCE_MAP_CHECKSUM_MST": "322", "F_AREA_MST": "611",
        }
        with patch.dict(os.environ, {"FFBE_ANDROID_EMBEDDED": "1"}, clear=False), \
                patch.object(ffbe_battle, "version_table", return_value=shipped), \
                patch.object(ios_tables, "android_vortex_bumps", return_value={"F_AREA_MST": 1777}), \
                patch.object(ffbe_battle, "_note"):
            output = ffbe_battle.serve_version_table(input_reply)
        self.assertIsNot(output, input_reply)
        self.assertEqual(output["other"], input_reply["other"])
        self.assertEqual(input_reply["c1qYg84Q"][2]["wM9AfX6I"], "219000")
        versions = {r["a4hXTIm0"]: r["wM9AfX6I"] for r in output["c1qYg84Q"]}
        self.assertEqual(versions, {
            "F_APP_VERSION_AND": "1167",
            "F_MST_VERSION": "0",
            **shipped,
            "F_AREA_MST": "2388",
        })
        self.assertNotIn("F_NEVER_SHIPPED", versions)

    def test_vortex_patch_allowlist_does_not_activate_unrelated_ios_tables(self):
        with patch.dict(os.environ, {"EXVIUS_IOS_HCA": "0",
                                     "EXVIUS_IOS_HCA_PLAIN": "0",
                                     "EXVIUS_IOS_DROP_UNVERSIONED": "0",
                                     "EXVIUS_IOS_SOUND_REFETCH": ""}, clear=False):
            allowed = ios_tables.ANDROID_VORTEX_TABLES
            self.assertEqual(allowed, {"F_RESOURCE_MST",
                                       "F_RESOURCE_VERSION_MST_LOCALIZE",
                                       "F_RESOURCE_CHECKSUM_MST", "F_AREA_MST"})
            self.assertTrue(ios_tables.android_vortex_wants(
                "/mst/Ver611_Fvix6V0n.dat"))
            self.assertFalse(ios_tables.android_vortex_wants(
                "/mst/Ver527_24Eka6wL.dat"))

    def test_missing_shipped_registry_fails_closed(self):
        with patch.dict(os.environ, {"FFBE_ANDROID_EMBEDDED": "1"}, clear=False), \
                patch.object(ffbe_battle, "version_table", return_value={}):
            with self.assertRaisesRegex(RuntimeError, "native MST version"):
                ffbe_battle.serve_version_table({"c1qYg84Q": []})

    def test_android_overlay_keeps_client_native_cache_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            data = home / "data"
            native = data / "native"
            (native / "mst").mkdir(parents=True)
            (native / "common_lang").mkdir(parents=True)
            (data / "static/mst_decoded").mkdir(parents=True)
            with patch.object(serve, "DATA", data), \
                    patch.object(serve, "ROOT", home / "server-root"), \
                    patch.dict(os.environ, {"FFBE_ANDROID_EMBEDDED": "1"}, clear=False):
                before = list(sys.path)
                try:
                    serve.configure_engine()
                    self.assertEqual(os.environ["CDN_ROOT"], str(native))
                    self.assertEqual(os.environ["CDN_OVERLAY"],
                                     str(home / "server-root/overlay"))
                finally:
                    sys.path[:] = before
            with patch.object(serve, "DATA", data), \
                    patch.object(serve, "ROOT", home / "server-root"), \
                    patch.dict(os.environ, {"FFBE_ANDROID_EMBEDDED": "0"}, clear=False):
                before = list(sys.path)
                try:
                    serve.configure_engine()
                    self.assertEqual(os.environ["CDN_ROOT"], str(native))
                    self.assertEqual(os.environ["CDN_OVERLAY"], str(native))
                finally:
                    sys.path[:] = before


if __name__ == "__main__":
    unittest.main(verbosity=2)
