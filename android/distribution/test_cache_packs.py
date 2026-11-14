"""No-network tests for externally cached FFBE ZIP distribution."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cache_packs


class CachePacksTests(unittest.TestCase):
    def manifest(self, root: Path):
        content = b"small-pack"
        sha = hashlib.sha256(content).hexdigest()
        packs = [
            {"id": "client-assets" if i == 0 else f"data-{i:03}",
             "sha256": sha, "size": len(content),
             "url": "https://github.com/Elvlin/exvius-offline/releases/download/test/a.zip"}
            for i in range(19)
        ]
        path = root / "manifest.json"
        path.write_text(json.dumps({"schema": 1, "revision": 9, "packs": packs}))
        return path, content

    def test_manifest_requires_19_and_safe_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, content = self.manifest(Path(tmp))
            self.assertEqual(len(cache_packs.read_packs(path)), 19)
            manifest = json.loads(path.read_text())
            manifest["packs"][0]["id"] = "../escape"
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                cache_packs.read_packs(path)

    def test_revision_10_cache_reuses_19_existing_zips(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, data = self.manifest(root)
            original = json.loads(manifest.read_text())
            original["revision"] = 10
            extra = dict(original["packs"][-1], id="summon-art")
            original["packs"].append(extra)
            manifest.write_text(json.dumps(original))
            self.assertEqual(len(cache_packs.read_packs(manifest)), 20)
            cache = root / "packs"
            cache.mkdir()
            for entry in original["packs"][:-1]:
                (cache / (entry["id"] + ".zip")).write_bytes(data)
            with patch.object(cache_packs.fetch_data, "download",
                              side_effect=lambda url, path, size: path.write_bytes(data)) as download:
                self.assertEqual(cache_packs.main([
                    "--manifest", str(manifest), "--destination", str(cache)
                ]), 0)
                download.assert_called_once()
            self.assertEqual(len(list(cache.glob("*.zip"))), 20)

    def test_verify_does_not_download_or_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, data = self.manifest(root)
            cache = root / "packs"
            cache.mkdir()
            with patch.object(cache_packs.fetch_data, "download") as download:
                self.assertEqual(cache_packs.main([
                    "--manifest", str(path), "--destination", str(cache),
                    "--verify-only", "--only", "client-assets"
                ]), 1)
                download.assert_not_called()
            self.assertFalse(list(cache.iterdir()))

    def test_download_reuses_upstream_and_verifies_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, data = self.manifest(root)
            cache = root / "packs"
            def emulate(url, dest, size):
                dest.write_bytes(data)
            with patch.object(cache_packs.fetch_data, "download", side_effect=emulate) as download:
                self.assertEqual(cache_packs.main([
                    "--manifest", str(path), "--destination", str(cache),
                    "--only", "client-assets",
                ]), 0)
                self.assertEqual(cache_packs.main([
                    "--manifest", str(path), "--destination", str(cache),
                    "--only", "client-assets",
                ]), 0)
                download.assert_called_once()
            self.assertEqual((cache / "client-assets.zip").read_bytes(), data)

    def test_corrupted_cache_rejected_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, data = self.manifest(root)
            cache = root / "packs"
            cache.mkdir()
            (cache / "client-assets.zip").write_bytes(b"corrupt")
            self.assertEqual(cache_packs.main([
                "--manifest", str(path), "--destination", str(cache),
                "--verify-only", "--only", "client-assets"
            ]), 1)
            self.assertEqual((cache / "client-assets.zip").read_bytes(), b"corrupt")

    def test_partial_symlink_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, data = self.manifest(root)
            cache = root / "packs"
            cache.mkdir()
            external = root / "external"
            external.write_bytes(b"untouched")
            (cache / "client-assets.part").symlink_to(external)
            with self.assertRaisesRegex(ValueError, "symlink"):
                cache_packs.main([
                    "--manifest", str(path), "--destination", str(cache),
                    "--only", "client-assets"
                ])
            self.assertEqual(external.read_bytes(), b"untouched")

    def test_symlink_cache_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, data = self.manifest(root)
            cache = root / "packs"
            cache.mkdir()
            external = root / "external"
            external.write_bytes(data)
            (cache / "client-assets.zip").symlink_to(external)
            with self.assertRaisesRegex(ValueError, "symlink"):
                cache_packs.main([
                    "--manifest", str(path), "--destination", str(cache),
                    "--only", "client-assets"
                ])


if __name__ == "__main__":
    unittest.main()
