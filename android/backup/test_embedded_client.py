"""Offline-only tests for Android backup pairing and worker.

No real device, no server credentials, no network outside 127.0.0.1.
"""
from __future__ import annotations
import contextlib
import http.client
import io
import json
import os
import pathlib
import socketserver
import ssl
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parent))
sys.modules.setdefault("ffbe_backup_transport", __import__("lxc_backup"))
import embedded_client as client

CERT = """-----BEGIN CERTIFICATE-----
MIIB
-----END CERTIFICATE-----"""

class EmbeddedClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.private = root / "private"
        self.state = root / "state"
        self.state.mkdir()
        (self.state / "campaign.json").write_text('{"hero":"Rain"}')
        self.worker = client.BackupCoordinator(self.private, self.state, interval=0.05)

    def tearDown(self):
        self.worker.stop()
        self.tmp.cleanup()

    @staticmethod
    def config(pem=None):
        return {"endpoint": "https://proxmox.tailcf6a16.ts.net:18447",
                "token": "A" * 48, "device": "samsung-android",
                "ca_pem": pem or CERT}

    def test_disabled_by_default_and_no_secret_file(self):
        self.assertFalse(self.worker.enabled())
        self.assertFalse(self.worker.poll_once())
        self.assertFalse(self.private.exists())

    def test_refuses_non_pinned_destination(self):
        for url in ("http://proxmox.tailcf6a16.ts.net:18447",
                    "https://evil.example:18447",
                    "https://proxmox.tailcf6a16.ts.net:8444",
                    "https://proxmox.tailcf6a16.ts.net:18447/a",
                    "https://user@proxmox.tailcf6a16.ts.net:18447"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                data = self.config()
                data["endpoint"] = url
                client._validated_config(data)

    def test_refuses_short_token(self):
        data = self.config()
        data["token"] = "bad"
        with self.assertRaises(ValueError):
            client._validated_config(data)

    def test_pair_requires_challenge_and_is_single_use(self):
        with mock.patch.object(ssl, "PEM_cert_to_DER_cert", return_value=b"x"):
            with self.assertRaises(PermissionError):
                self.worker.pair(self.config(), "incorrect")
            self.worker.pair(self.config(), self.worker._pair_nonce)
        self.assertTrue(self.worker.enabled())
        self.assertEqual(self.worker.config_file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.worker.ca_file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.private.stat().st_mode & 0o777, 0o700)
        self.assertNotIn("A" * 48, json.dumps(self.worker.status()))
        with self.assertRaises(PermissionError):
            self.worker.pair(self.config(), self.worker._pair_nonce)

    def test_expired_or_too_many_attempts_refused(self):
        self.worker._pair_deadline = time.monotonic() - 1
        with self.assertRaises(PermissionError):
            self.worker.pair(self.config(), self.worker._pair_nonce)

    def test_snapshot_signature_changes_with_save(self):
        first = client._signature(self.state)
        (self.state / "campaign.json").write_text('{"hero":"Lasswell","turn":9}')
        self.assertNotEqual(first, client._signature(self.state))

    def test_snapshot_refuses_save_symlink(self):
        (self.state / "other.json").symlink_to(self.state / "campaign.json")
        with self.assertRaises(ValueError):
            client._signature(self.state)

    def _provision(self):
        # Private files are prepared exactly as the authenticated pairing
        # endpoint does, with a synthetic certificate and token.
        with mock.patch.object(ssl, "PEM_cert_to_DER_cert", return_value=b"x"):
            self.worker.pair(self.config(), self.worker._pair_nonce)

    def test_async_upload_ack_and_no_duplicate(self):
        self._provision()
        result = {"sha256": "f" * 64, "files": ["campaign.json"]}
        with mock.patch.object(ssl, "PEM_cert_to_DER_cert", return_value=b"x"):
            with mock.patch.object(client.transport, "upload", return_value=result) as upload:
                self.assertTrue(self.worker.poll_once())
                self.assertFalse(self.worker.poll_once())
                upload.assert_called_once()
        self.assertEqual(json.loads(self.worker.status_file.read_text())["sha256"], result["sha256"])
        self.assertNotIn("A" * 48, self.worker.status_file.read_text())

    def test_retry_does_not_block_game(self):
        self._provision()
        with mock.patch.object(ssl, "PEM_cert_to_DER_cert", return_value=b"x"):
            with mock.patch.object(client.transport, "upload", side_effect=OSError("private server unreachable")):
                self.assertFalse(self.worker.poll_once())
                self.assertEqual(self.worker.status()["last_error"], "OSError")
                self.assertFalse(self.worker.poll_once())
        self.assertFalse(self.worker.status()["last_backup"])

    def test_rejects_insecure_credentials_permissions(self):
        self._provision()
        os.chmod(self.worker.config_file, 0o644)
        with self.assertRaises(ValueError):
            self.worker._load()

    def test_wrap_handler_preserves_game_routes(self):
        class Original(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                self.send_response(204)
                self.end_headers()
            def do_POST(self):
                self.send_response(204)
                self.end_headers()
        Handler = client.wrap_handler(Original, self.worker)
        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address
            conn = http.client.HTTPConnection(host, port, timeout=2)
            conn.request("GET", "/game")
            self.assertEqual(conn.getresponse().status, 204)
            conn.request("GET", client.STATUS_PATH)
            reply = conn.getresponse()
            self.assertEqual(reply.status, 200)
            self.assertFalse(json.loads(reply.read())["configured"])
            conn.request("POST", client.PAIR_PATH,
                         body=json.dumps(self.config()),
                         headers={"Content-Type": "application/json",
                                  "X-FFBE-Pair-Code": "bad"})
            self.assertEqual(conn.getresponse().status, 403)
            conn.request("POST", "/game", body=b"abc")
            self.assertEqual(conn.getresponse().status, 204)
            server.shutdown()
            conn.close()

if __name__ == "__main__":
    unittest.main()
