"""Private APK LAN delivery contracts; synthetic bytes, no real game binaries."""
from __future__ import annotations

import contextlib
import hashlib
import io
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from apk_lan import valid_lan_ip, validated_artifact
from local_cache_server import make_handler


class PrivateLanApkTests(unittest.TestCase):
    def test_binding_requires_private_explicit_lan_ipv4(self):
        self.assertEqual(valid_lan_ip("192.168.15.209"), "192.168.15.209")
        for forbidden in ("127.0.0.1", "0.0.0.0", "8.8.8.8", "224.0.0.1", "::1"):
            with self.subTest(forbidden=forbidden), self.assertRaises(ValueError):
                valid_lan_ip(forbidden)

    def test_only_verified_regular_apk_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            apk = root / "FFBE-Private.apk"
            content = b"safe synthetic fixture"
            apk.write_bytes(content)
            digest = hashlib.sha256(content).hexdigest()
            self.assertEqual(validated_artifact(apk, digest), (apk, len(content), digest))
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                validated_artifact(apk, "0" * 64)
            link = root / "Linked.apk"
            link.symlink_to(apk)
            with self.assertRaisesRegex(ValueError, "regular"):
                validated_artifact(link, digest)
            invalid = root / "../escape.apk"
            with self.assertRaises(ValueError):
                validated_artifact(invalid, digest)

    def test_apk_access_token_range_metadata_and_no_cache_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            apk = Path(tmp) / "Private-FFBE.apk"
            content = b"test-only APK data" * 75
            apk.write_bytes(content)
            digest = hashlib.sha256(content).hexdigest()
            data = validated_artifact(apk, digest)
            capability = "synthetic-secret-capability"
            handler = make_handler(b"", {}, apk=data, token=capability,
                                   expires_at=time.monotonic()+30)
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            server.daemon_threads = True
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            address = f"{base}/download/{capability}/{apk.name}"
            try:
                for forbidden in (base+"/data/latest.json", base+"/packs/data-001.zip",
                                  base+"/download/wrong/"+apk.name,
                                  address+"?leak=1"):
                    with self.subTest(url=forbidden), self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(forbidden, timeout=3)
                    self.assertEqual(error.exception.code, 404)
                with urllib.request.urlopen(address, timeout=3) as reply:
                    self.assertEqual(reply.status, 200)
                    self.assertEqual(reply.headers["X-Checksum-SHA256"], digest)
                    self.assertIn(apk.name, reply.headers["Content-Disposition"])
                    self.assertEqual(reply.headers["Accept-Ranges"], "bytes")
                    self.assertEqual(reply.read(), content)
                req = urllib.request.Request(address, headers={"Range":"bytes=38-"})
                with urllib.request.urlopen(req, timeout=3) as reply:
                    self.assertEqual(reply.status, 206)
                    self.assertEqual(reply.headers["Content-Range"],
                                     f"bytes 38-{len(content)-1}/{len(content)}")
                    self.assertEqual(reply.read(), content[38:])
                with urllib.request.urlopen(urllib.request.Request(
                        address, method="HEAD"), timeout=3) as reply:
                    self.assertEqual(reply.status, 200)
                    self.assertEqual(reply.headers["Content-Length"], str(len(content)))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(3)

    def test_expired_capability_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            apk = Path(tmp) / "Private-FFBE.apk"
            apk.write_bytes(b"fake apk")
            data = validated_artifact(apk, hashlib.sha256(b"fake apk").hexdigest())
            server = ThreadingHTTPServer(("127.0.0.1", 0),
                make_handler(b"", {}, apk=data, token="expired",
                             expires_at=time.monotonic()-1))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                address = f"http://127.0.0.1:{server.server_port}/download/expired/{apk.name}"
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(address, timeout=3)
                self.assertEqual(error.exception.code, 404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(3)

    def test_apk_capability_is_not_written_to_logs(self):
        handler = make_handler(b"", {}, apk=(Path("Demo.apk"), 1, "a"*64),
                               token="DO_NOT_LOG_THIS", expires_at=time.monotonic()+30)
        obj = object.__new__(handler)
        with io.StringIO() as output, contextlib.redirect_stdout(output):
            obj.log_message("%s", "/download/DO_NOT_LOG_THIS/Demo.apk")
            self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
