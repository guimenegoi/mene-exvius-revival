"""Offline contract tests: private ZIP cache, manifest pinning and HTTP Range."""
from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from local_cache_server import make_handler, pinned_data


class LocalCacheTests(unittest.TestCase):
    def fixture(self, root: Path):
        files = root / "packs"
        files.mkdir()
        packs = []
        for n in range(19):
            name = "client-assets" if n == 0 else f"data-{n:03}"
            content = f"verified-{name}".encode()
            (files / f"{name}.zip").write_bytes(content)
            packs.append({"id": name, "size": len(content),
                          "sha256": hashlib.sha256(content).hexdigest(),
                          "url": f"https://github.com/test/{name}.zip",
                          "unpackedSize": len(content)})
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps({"schema": 1, "revision": 9, "packs": packs}))
        return manifest, files

    def test_rewrites_only_urls(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest, files = self.fixture(Path(temp))
            body, indexed = pinned_data(manifest, files, "http://127.0.0.1:18082")
            original = json.loads(manifest.read_text())
            current = json.loads(body)
            self.assertEqual(len(indexed), 19)
            for previous, result in zip(original["packs"], current["packs"]):
                self.assertEqual(result["id"], previous["id"])
                self.assertEqual(result["sha256"], previous["sha256"])
                self.assertEqual(result["size"], previous["size"])
                self.assertEqual(result["unpackedSize"], previous["unpackedSize"])
                self.assertEqual(result["url"], f"http://127.0.0.1:18082/packs/{result['id']}.zip")

    def test_rejects_bad_pack_size_and_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest, files = self.fixture(Path(temp))
            bad = files / "client-assets.zip"
            bad.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "incorrect"):
                pinned_data(manifest, files, "http://127.0.0.1:18082")
            bad.unlink()
            bad.symlink_to(manifest)
            with self.assertRaisesRegex(ValueError, "linked"):
                pinned_data(manifest, files, "http://127.0.0.1:18082")

    def test_http_bytes_and_range_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest, files = self.fixture(Path(temp))
            data, paths = pinned_data(manifest, files, "http://127.0.0.1:18082")
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(data, paths))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            try:
                thread.start()
                base = "http://127.0.0.1:" + str(server.server_address[1])
                with urllib.request.urlopen(base + "/data/latest.json") as r:
                    self.assertEqual(r.status, 200)
                    self.assertEqual(r.read(), data)
                name = "data-001"
                original = (files / f"{name}.zip").read_bytes()
                with urllib.request.urlopen(base + f"/packs/{name}.zip") as r:
                    self.assertEqual(r.status, 200)
                    self.assertEqual(r.read(), original)
                request = urllib.request.Request(base + f"/packs/{name}.zip",
                                                 headers={"Range": "bytes=4-"})
                with urllib.request.urlopen(request) as r:
                    self.assertEqual(r.status, 206)
                    self.assertEqual(r.headers["Content-Range"],
                                     f"bytes 4-{len(original)-1}/{len(original)}")
                    self.assertEqual(r.read(), original[4:])
                request = urllib.request.Request(base + f"/packs/{name}.zip",
                                                 headers={"Range": f"bytes={len(original)}-"})
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request)
                self.assertEqual(error.exception.code, 416)
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(base + "/packs/../../etc/passwd")
                with urllib.request.urlopen(urllib.request.Request(
                        base + f"/packs/{name}.zip", method="HEAD")) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers["Content-Length"], str(len(original)))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(3)
            self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
