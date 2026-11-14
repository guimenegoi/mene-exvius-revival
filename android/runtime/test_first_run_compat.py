"""Upstream Java first-run receipts -> the existing private Revival data layout."""
from __future__ import annotations

import hashlib
import importlib
import json
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import local_http
from test_local_http import sample

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "ios-server"))
sys.path.insert(0, str(REPO / "android/data"))
import offline_data  # noqa: E402


def upstream_fixture(root: Path):
    archive, files, manifest = sample(root)
    manifest["revision"] = 10
    for record in manifest["packs"]:
        record["unpackedSize"] = 10
    asset = files / "exvius/data/static/client/game-assets.apk"
    client = next(p for p in manifest["packs"] if p["id"] == "client-assets")
    client["unpackedSize"] = asset.stat().st_size
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(local_http.DATA_MANIFEST, json.dumps(manifest),
                        compress_type=zipfile.ZIP_STORED)
    data = files / "exvius/data"
    installed = {"schema": 1, "revision": 10,
                 "packs": [dict(p) for p in manifest["packs"]]}
    (data / "installed.json").write_text(json.dumps(installed))
    (data / "offline-client-assets.json").unlink()
    for link in (data / "native").iterdir():
        link.unlink()
    (data / "native").rmdir()
    return archive, files, manifest, asset


class FirstRunCompatTests(unittest.TestCase):
    def mock_native_engine(self, archive: Path, files: Path, asset: Path):
        class Bootstrap:
            @staticmethod
            def install(archive, target):
                (target / "ios-server").mkdir(parents=True, exist_ok=True)
                (target / "android/data").mkdir(parents=True, exist_ok=True)
                return 2

        original_import = importlib.import_module

        def load(name):
            if name == "ffbe_engine_bootstrap":
                return Bootstrap
            if name == "offline_data":
                return offline_data
            return original_import(name)

        return (patch.object(local_http, "EXPECTED_CLIENT_SIZE", asset.stat().st_size),
                patch.object(local_http, "EXPECTED_CLIENT_SHA256",
                             hashlib.sha256(asset.read_bytes()).hexdigest()),
                patch.object(local_http, "EXPECTED_CLIENT_PACK_SHA256",
                             local_http._manifest(archive)["packs"][0]["sha256"]),
                patch.object(local_http.importlib, "import_module", side_effect=load))

    def test_android_receipt_is_accepted_by_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, files, manifest, asset = upstream_fixture(Path(tmp))
            # A finished Java install is not yet prepared for the Python server.
            self.assertFalse(local_http.preflight(archive, files)[0])
            patches = self.mock_native_engine(archive, files, asset)
            from contextlib import ExitStack
            before = list(sys.path)
            try:
                with ExitStack() as stack:
                    for item in patches:
                        stack.enter_context(item)
                    ok, msg = local_http.reconcile_first_run(archive, files)
                    self.assertTrue(ok, msg)
                    self.assertIn("reconciled", msg)
                    valid, msg = local_http.preflight(archive, files)
                    self.assertTrue(valid, msg)
                    again, reason = local_http.reconcile_first_run(archive, files)
                    self.assertFalse(again)
                    self.assertIn("already reconciled", reason)
                    for name in local_http.NATIVE_NAMES:
                        self.assertTrue((files / "exvius/data/native" / name).is_symlink())
                    # No fake server and no saves during the adapter.
                    self.assertFalse((files / "exvius/server-root").exists())
                    self.assertEqual(json.loads((files / "exvius/data/installed.json").read_text())
                                     ["revision"], 10)
            finally:
                sys.path[:] = before

    def test_reject_incorrect_pack_or_duplicate_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, files, manifest, asset = upstream_fixture(Path(tmp))
            data = files / "exvius/data"
            receipt = data / "installed.json"
            current = json.loads(receipt.read_text())
            current["packs"][1]["sha256"] = "0" * 64
            receipt.write_text(json.dumps(current))
            ok, reason = local_http.reconcile_first_run(archive, files)
            self.assertFalse(ok)
            self.assertIn("not all", reason)
            self.assertFalse((data / "native").exists())
            current["packs"][1]["sha256"] = manifest["packs"][1]["sha256"]
            current["packs"][1]["id"] = "client-assets"
            receipt.write_text(json.dumps(current))
            self.assertFalse(local_http.preflight(archive, files)[0])
            self.assertFalse(local_http.reconcile_first_run(archive, files)[0])

    def test_reject_corrupted_client_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, files, manifest, asset = upstream_fixture(Path(tmp))
            size = asset.stat().st_size
            expected = hashlib.sha256(asset.read_bytes()).hexdigest()
            asset.write_bytes(b"x" * size)
            with patch.object(local_http, "EXPECTED_CLIENT_SIZE", size), \
                    patch.object(local_http, "EXPECTED_CLIENT_SHA256", expected), \
                    patch.object(local_http, "EXPECTED_CLIENT_PACK_SHA256",
                                 manifest["packs"][0]["sha256"]):
                ok, reason = local_http.reconcile_first_run(archive, files)
            self.assertFalse(ok)
            self.assertIn("SHA", reason)
            data = files / "exvius/data"
            self.assertFalse((data / "native").exists())
            self.assertFalse((data / "offline-client-assets.json").exists())

    def test_reject_private_static_symlink_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, files, manifest, asset = upstream_fixture(Path(tmp))
            data = files / "exvius/data"
            client_dir = data / "static/client"
            # Symlink ancestors are refused even when the referenced file
            # exists and has the expected bytes.
            real = client_dir.with_name("client-real")
            client_dir.rename(real)
            client_dir.symlink_to(real, target_is_directory=True)
            ok, reason = local_http.reconcile_first_run(archive, files)
            self.assertFalse(ok)
            self.assertIn("private data", reason)
            self.assertFalse((data / "native").exists())
            self.assertFalse((data / "offline-client-assets.json").exists())

    def test_reject_wrong_revision_without_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, files, manifest, asset = upstream_fixture(Path(tmp))
            receipt = files / "exvius/data/installed.json"
            current = json.loads(receipt.read_text())
            current["revision"] = 9
            receipt.write_text(json.dumps(current))
            ok, reason = local_http.reconcile_first_run(archive, files)
            self.assertFalse(ok)
            self.assertIn("revision", reason)
            self.assertFalse((files / "exvius/server-root").exists())

    def test_python_dict_install_remains_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, files, manifest = sample(Path(tmp))
            ok, reason = local_http.reconcile_first_run(archive, files)
            self.assertFalse(ok)
            self.assertIn("canonical", reason)
            self.assertTrue(local_http.preflight(archive, files)[0])


if __name__ == "__main__":
    unittest.main()
