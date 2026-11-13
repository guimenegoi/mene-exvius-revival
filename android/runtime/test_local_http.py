"""Readiness, fail-closed startup and loopback wiring of the Android Revival HTTP adapter.

The live socket test uses a stub handler and must NOT be confused with
proving the real 19-pack Revival engine or offline gameplay.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import local_http


def sample(root: Path) -> tuple[Path, Path, dict]:
    files = root / "files"
    archive = files / "ffbe_python/stdlib.zip"
    archive.parent.mkdir(parents=True)
    data = files / "exvius/data"
    data.mkdir(parents=True)
    packs = [{"id": "client-assets" if i == 0 else f"data-{i:03}",
              "sha256": f"{i + 1:064x}"} for i in range(19)]
    manifest = {"schema": 1, "packs": packs, "files": 11}
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(local_http.DATA_MANIFEST, json.dumps(manifest),
                    compress_type=zipfile.ZIP_STORED)
    (data / "installed.json").write_text(json.dumps(
        {p["id"]: p["sha256"] for p in packs}
    ))
    for name in local_http.NATIVE_NAMES:
        (files / name).mkdir(parents=True)
        (data / "native").mkdir(exist_ok=True)
        (data / "native" / name).symlink_to("../../../" + name,
                                             target_is_directory=True)
    resources = {
        "mst/f_unit.dat": b"data",
        "mst/Ver709_i5QEJpua.dat": b"data-pack-011",
        "mst/Ver9001_YW9MUm2H.dat": b"story-movies-pack",
        "localized_texts/en/unit.dat": b"data",
        "en/sd/area/area.cpk": b"data",
        "en/sd/area/Ver461_spdungeon1.cpk": b"original-cpk",
        "common_lang/game.cpk": b"data",
        "homeMarquee/banner.cpk": b"data",
    }
    for name, value in resources.items():
        target = files / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    statics = {path: b"valid" for path in local_http.REQUIRED_FILES}
    statics["static/text_decoded/unit.txt"] = b"localized"
    statics["static/client/game-assets.apk"] = b"client-assets-demo"
    for name, value in statics.items():
        target = data / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    value = statics["static/client/game-assets.apk"]
    (data / "offline-client-assets.json").write_text(json.dumps({
        "archive_sha256": packs[0]["sha256"],
        "file": "static/client/game-assets.apk",
        "file_size": len(value),
        "file_sha256": hashlib.sha256(value).hexdigest(),
    }))
    (data / "registry.json").write_text("{}")
    return archive, files, manifest


class LoopbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"revival-handler-routed"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class LocalHttpTests(unittest.TestCase):
    def test_missing_data_fails_before_any_server_or_save_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "ffbe_python/stdlib.zip"
            archive.parent.mkdir(parents=True)
            archive.write_bytes(b"not needed")
            ready, reason = local_http.preflight(archive, root)
            self.assertFalse(ready)
            self.assertIn("data root", reason)
            with self.assertRaisesRegex(RuntimeError, "Refusing Revival HTTP"):
                local_http.run(archive, root)
            self.assertFalse((root / "exvius/server-root").exists())

    def test_installed_pack_receipts_and_native_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, files, manifest = sample(Path(tmp))
            ok, msg = local_http.preflight(archive, files)
            self.assertTrue(ok, msg)
            self.assertIn("19-pack", msg)
            receipt = files / "exvius/data/installed.json"
            record = json.loads(receipt.read_text())
            del record["data-001"]
            receipt.write_text(json.dumps(record))
            self.assertFalse(local_http.preflight(archive, files)[0])
            self.assertFalse((files / "exvius/server-root").exists())

    def test_malformed_android_receipt_reports_the_rejected_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, files, manifest = sample(Path(tmp))
            records = [
                dict(pack, unpackedSize=10) for pack in manifest["packs"]
            ]
            records[8]["unpackedSize"] = 0
            (files / "exvius/data/installed.json").write_text(json.dumps({
                "schema": 1, "revision": 9, "packs": records,
            }))
            ready, reason = local_http.preflight(archive, files)
            self.assertFalse(ready)
            self.assertIn("ValueError", reason)
            self.assertIn("index 8", reason)
            self.assertIn("unpackedSize=0", reason)
            self.assertFalse((files / "exvius/server-root").exists())

    def test_missing_receipt_reports_prior_reconciliation_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, files, _ = sample(Path(tmp))
            (files / "exvius/data/offline-client-assets.json").unlink()
            import __main__
            with patch.object(__main__, "_first_run_reason",
                              "first-run adapter refused: ValueError: failed to link",
                              create=True):
                ready, reason = local_http.preflight(archive, files)
            self.assertFalse(ready)
            self.assertIn("offline-client-assets.json", reason)
            self.assertIn("failed to link", reason)
            self.assertFalse((files / "exvius/server-root").exists())

    def test_client_hash_and_file_inventory_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, files, manifest = sample(Path(tmp))
            asset = files / "exvius/data/static/client/game-assets.apk"
            asset.write_bytes(b"changed")
            self.assertIn("receipt", local_http.preflight(archive, files)[1])
            asset.write_bytes(b"client-assets-demX")
            self.assertIn("hash mismatch", local_http.preflight(archive, files)[1])
            asset.write_bytes(b"client-assets-demo")
            with zipfile.ZipFile(archive, "w") as zf:
                manifest["files"] = 100_000
                zf.writestr(local_http.DATA_MANIFEST, json.dumps(manifest),
                            compress_type=zipfile.ZIP_STORED)
            self.assertIn("inventory incomplete", local_http.preflight(archive, files)[1])

    def test_rejects_native_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, files, _ = sample(Path(tmp))
            link = files / "exvius/data/native/mst"
            link.unlink()
            link.symlink_to("/tmp", target_is_directory=True)
            self.assertIn("native resource link invalid",
                          local_http.preflight(archive, files)[1])

    def test_cdn_overlay_hardlinks_survive_client_cache_eviction(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, files, _ = sample(Path(tmp))
            original = files / "mst/Ver709_i5QEJpua.dat"
            preserved = files / "exvius/server-root/overlay/mst/Ver709_i5QEJpua.dat"
            count = local_http.preserve_native_mst_for_cdn(files)
            self.assertEqual(count, 4)
            pinned_pack = files / "exvius/server-root/overlay/en/sd/area/Ver461_spdungeon1.cpk"
            self.assertTrue(os.path.samefile(
                pinned_pack, files / "en/sd/area/Ver461_spdungeon1.cpk"))
            self.assertTrue(os.path.samefile(original, preserved))
            original.unlink()
            self.assertEqual(preserved.read_bytes(), b"data-pack-011")
            self.assertEqual(local_http.preserve_native_mst_for_cdn(files), 0)

    def test_cdn_overlay_falls_back_to_atomic_copy_when_hardlinks_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, files, _ = sample(Path(tmp))
            original = files / "mst/Ver709_i5QEJpua.dat"
            pinned = files / "exvius/server-root/overlay/mst/Ver709_i5QEJpua.dat"
            cpk = files / "en/sd/area/Ver461_spdungeon1.cpk"
            pinned_cpk = files / "exvius/server-root/overlay/en/sd/area/Ver461_spdungeon1.cpk"
            with patch.object(local_http.os, "link",
                              side_effect=PermissionError(errno.EACCES, "Android denies hardlinks")):
                self.assertEqual(local_http.preserve_native_mst_for_cdn(files), 4)
            self.assertEqual(original.read_bytes(), pinned.read_bytes())
            self.assertNotEqual(original.stat().st_ino, pinned.stat().st_ino)
            self.assertEqual(cpk.read_bytes(), pinned_cpk.read_bytes())
            self.assertNotEqual(cpk.stat().st_ino, pinned_cpk.stat().st_ino)
            self.assertFalse(pinned.with_name(pinned.name + ".copying").exists())
            original.unlink()
            cpk.unlink()
            self.assertEqual(pinned.read_bytes(), b"data-pack-011")
            self.assertEqual(pinned_cpk.read_bytes(), b"original-cpk")

    def test_cdn_overlay_does_not_hide_unrelated_hardlink_io_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, files, _ = sample(Path(tmp))
            with patch.object(local_http.os, "link",
                              side_effect=OSError(errno.EIO, "disk failure")):
                with self.assertRaises(OSError):
                    local_http.preserve_native_mst_for_cdn(files)
            self.assertFalse((files / "exvius/server-root/overlay/mst/f_unit.dat").exists())

    def test_cdn_overlay_refuses_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, files, _ = sample(Path(tmp))
            (files / "mst/f_unit.dat").unlink()
            (files / "mst/f_unit.dat").symlink_to("/etc/passwd")
            with self.assertRaisesRegex(ValueError, "contains symlink"):
                local_http.preserve_native_mst_for_cdn(files)

    def test_loopback_server_delegates_to_engine_handler(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, files, _ = sample(Path(tmp))
            used = []
            engines = []
            servers = []
            target = archive.parent / "engine"

            def setup(_archive: Path, engine: Path):
                used.append("verified-sha-installer")
                for relative in ("vendor", "source/server", "ios-server"):
                    (engine / relative).mkdir(parents=True, exist_ok=True)

            fake_bootstrap = types.SimpleNamespace(install=setup)

            def fake_import(name):
                if name == "ffbe_engine_bootstrap":
                    return fake_bootstrap
                if name == "serve":
                    return fake_serve
                raise AssertionError("Unplanned module: " + name)

            def factory(address, handler):
                self.assertEqual(address, ("127.0.0.1", 18080))
                self.assertIs(handler, LoopbackHandler)
                server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
                servers.append(server)
                return server

            def configure():
                engines.append("configure")

            def start_engine():
                engines.append("real-engine-entrypoint")
                return "capture"

            def make_handler(capture, profile, der):
                self.assertEqual((capture, profile, der), ("capture", b"", b""))
                engines.append("handler")
                return LoopbackHandler

            fake_serve = types.SimpleNamespace(
                configure_engine=configure, start_engine=start_engine,
                make_handler=make_handler, Server=factory,
            )
            errors = []
            before = list(sys.path)
            with patch.object(local_http.importlib, "import_module", side_effect=fake_import), \
                    patch.dict(os.environ, {}, clear=False):
                thread = threading.Thread(
                    target=lambda: self._run_and_catch(
                        lambda: local_http.run(archive, files), errors,
                    ), daemon=True
                )
                try:
                    thread.start()
                    for _ in range(150):
                        if servers:
                            break
                        time.sleep(.02)
                    self.assertEqual(len(servers), 1)
                    url = f"http://127.0.0.1:{servers[0].server_address[1]}/ffbe/test"
                    with urllib.request.urlopen(url, timeout=2) as res:
                        self.assertEqual(res.read(), b"revival-handler-routed")
                    self.assertEqual(engines, [
                        "configure", "real-engine-entrypoint", "handler"
                    ])
                    self.assertEqual(used, ["verified-sha-installer"])
                    self.assertEqual(os.environ["FFBE_DATA_DIR"],
                                     str(files / "exvius/data"))
                    self.assertEqual(os.environ["FFBE_SERVER_ROOT"],
                                     str(files / "exvius/server-root"))
                finally:
                    if servers:
                        servers[0].shutdown()
                    thread.join(4)
                    sys.path[:] = before
            self.assertFalse(errors)
            self.assertFalse(thread.is_alive())

    @staticmethod
    def _run_and_catch(fn, errors):
        try:
            fn()
        except Exception as exc:
            errors.append(exc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
