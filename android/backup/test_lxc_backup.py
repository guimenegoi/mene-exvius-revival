"""Synthetic save-only contracts; never connects to the actual LXC or phone."""
import hashlib
import io
import json
import os
import ssl
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import lxc_backup as backup


def sample(root: Path) -> Path:
    state = root / "exvius/server-root/state"
    state.mkdir(parents=True)
    (state / "campaign.json").write_text(json.dumps({"progress": {"rank": 5}, "units": [100]}))
    (state / "replay.json").write_text('{"week": 2}')
    (state / "backups").mkdir()
    (state / "backups/old.json").write_text('{"not": "exported"}')
    return state


class BackupTests(unittest.TestCase):
    def test_collect_valid_and_no_unrelated_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = sample(Path(tmp))
            data = backup.snapshot(state)
            self.assertEqual(backup.validate(data), ["campaign.json", "replay.json"])
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                self.assertEqual(set(zf.namelist()),
                                 {"manifest.json", "state/campaign.json", "state/replay.json"})
                self.assertNotIn(b"not\x22: \x22exported", data)

    def test_temporary_atomic_save_is_not_uploaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = sample(Path(tmp))
            (state / "campaign.json.tmp").write_text('{"incomplete":')
            (state / "replay.json.tmp").write_text("partial write")
            data = backup.snapshot(state)
            self.assertEqual(backup.validate(data), ["campaign.json", "replay.json"])
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                self.assertEqual(sorted(zf.namelist()),
                                 ["manifest.json", "state/campaign.json", "state/replay.json"])
            self.assertNotIn(b"partial write", data)

    def test_temporary_files_do_not_consume_snapshot_slot_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = sample(Path(tmp))
            for i in range(backup.MAX_FILES):
                (state / f"stale_{i}.json.tmp").write_text("incomplete")
            self.assertEqual(backup.validate(backup.snapshot(state)),
                             ["campaign.json", "replay.json"])

    def test_too_many_actual_saves_are_still_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = sample(Path(tmp))
            for i in range(backup.MAX_FILES):
                (state / f"extra_{i}.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "Too many save files"):
                backup.snapshot(state)

    def test_symlink_atomic_temporary_save_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = sample(Path(tmp))
            (state / "campaign.json.tmp").symlink_to(Path(tmp) / "outside")
            with self.assertRaisesRegex(ValueError, "temporary"):
                backup.snapshot(state)

    def test_snapshot_refuses_missing_campaign(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = sample(Path(tmp))
            (state / "campaign.json").unlink()
            with self.assertRaisesRegex(ValueError, "campaign"):
                backup.snapshot(state)

    def test_refuses_symlink_and_unexpected_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = sample(Path(tmp))
            (state / "campaign.json").unlink()
            (state / "campaign.json").symlink_to(Path(tmp) / "escape")
            with self.assertRaises(ValueError):
                backup.snapshot(state)
            (state / "campaign.json").unlink()
            (state / "campaign.json").write_text("{}")
            (state / "secret.pem").write_text("secret")
            with self.assertRaisesRegex(ValueError, "Unexpected file"):
                backup.snapshot(state)

    def test_bad_hash_and_name_and_zip_bomb_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = backup.snapshot(sample(Path(tmp)))
            with zipfile.ZipFile(io.BytesIO(base)) as original:
                meta = json.loads(original.read("manifest.json"))
                meta["files"]["campaign.json"] = "a" * 64
                replacements = {
                    "manifest.json": json.dumps(meta).encode(),
                    "state/campaign.json": original.read("state/campaign.json"),
                    "state/replay.json": original.read("state/replay.json"),
                }
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as zf:
                for name, data in replacements.items():
                    zf.writestr(name, data)
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                backup.validate(buffer.getvalue())
            with zipfile.ZipFile(io.BytesIO(base)) as original:
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w") as zf:
                    for name in original.namelist():
                        zf.writestr(name.replace("state/replay.json", "../replay.json"),
                                    original.read(name))
            with self.assertRaises(ValueError):
                backup.validate(buffer.getvalue())
            with zipfile.ZipFile(io.BytesIO(base)) as original:
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for name in original.namelist():
                        zf.writestr(name, original.read(name))
            with self.assertRaisesRegex(ValueError, "Compressed"):
                backup.validate(buffer.getvalue())

    def test_server_store_retention_private_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            state = sample(base)
            root = base / "storage"
            for i in range(4):
                (state / "campaign.json").write_text(json.dumps({"counter": i}))
                report = backup.store(backup.snapshot(state), root, "phone1", retention=2)
                self.assertEqual(report["files"], ["campaign.json", "replay.json"])
            archives = list((root / "phone1").glob("*.zip"))
            self.assertEqual(len(archives), 2)
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            self.assertTrue(all(x.stat().st_mode & 0o777 == 0o600 for x in archives))
            self.assertEqual(backup.validate(archives[0].read_bytes()),
                             ["campaign.json", "replay.json"])

    def test_unauthorized_and_bad_sha_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            state = sample(base)
            payload = backup.snapshot(state)
            server = ThreadingHTTPServer(("127.0.0.1", 0),
                         backup.make_handler(base / "stored", "a" * 32))
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            url = f"http://127.0.0.1:{server.server_port}/v1/backups/phone"
            try:
                for token, digest, code in [("wrong", hashlib.sha256(payload).hexdigest(), 401),
                                            ("a" * 32, "0" * 64, 400)]:
                    req = urllib.request.Request(url, data=payload, method="POST",
                        headers={"Authorization": "Bearer " + token,
                                 "Content-Type": "application/zip",
                                 "X-Content-SHA256": digest})
                    with self.assertRaises(urllib.error.HTTPError) as exc:
                        urllib.request.urlopen(req, timeout=2)
                    self.assertEqual(exc.exception.code, code)
                self.assertFalse((base / "stored").exists())
                req = urllib.request.Request(url, data=payload, method="POST",
                    headers={"Authorization": "Bearer " + "a" * 32,
                             "Content-Type": "application/zip",
                             "X-Content-SHA256": hashlib.sha256(payload).hexdigest()})
                with urllib.request.urlopen(req, timeout=2) as res:
                    self.assertEqual(res.status, 201)
                    receipt = json.load(res)
                self.assertEqual(receipt["sha256"], hashlib.sha256(payload).hexdigest())
                req = urllib.request.Request(url, headers={"Authorization": "Bearer " + "a" * 32})
                with urllib.request.urlopen(req, timeout=2) as res:
                    self.assertEqual(len(json.load(res)["backups"]), 1)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(2)

    def test_client_rejects_http_even_on_local_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = sample(Path(tmp))
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                backup.upload(state, "http://127.0.0.1:18447", "token", Path(tmp), "phone")

    def test_end_to_end_https_with_pinned_ca(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cert, key = base / "server.pem", base / "server.key"
            subprocess.run(["openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048",
                            "-days", "1", "-keyout", str(key), "-out", str(cert),
                            "-subj", "/CN=ffbe-test",
                            "-addext", "subjectAltName=IP:127.0.0.1"],
                           check=True, capture_output=True)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(str(cert), str(key))
            server = ThreadingHTTPServer(("127.0.0.1", 0),
                         backup.make_handler(base / "stored", "b" * 32))
            server.socket = context.wrap_socket(server.socket, server_side=True)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                with patch.dict(os.environ, {"no_proxy": "127.0.0.1"}, clear=False):
                    result = backup.upload(sample(base),
                        f"https://127.0.0.1:{server.server_port}",
                        "b" * 32, cert, "phone", timeout=4)
                self.assertEqual(len(result["files"]), 2)
                self.assertTrue((base / "stored/phone" / result["id"]).is_file())
                with self.assertRaises(ssl.SSLError):
                    backup.upload(base / "exvius/server-root/state",
                        f"https://127.0.0.1:{server.server_port}",
                        "b" * 32, key, "phone", timeout=4)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(2)


if __name__ == "__main__":
    unittest.main()
