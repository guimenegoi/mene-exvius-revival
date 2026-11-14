#!/usr/bin/env python3
"""Small synthetic ZIP fixtures: never downloads real game binaries or data."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import offline_data


def pack(directory: Path, ident: str, contents: dict[str, bytes]) -> dict:
    archive = directory / f"{ident}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as z:
        for path, value in contents.items():
            z.writestr(path, value)
    return {
        "id": ident,
        "url": archive.as_uri(),
        "size": archive.stat().st_size,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    }


def fixture(directory: Path) -> tuple[Path, Path, dict]:
    data = directory / "app-data"
    sources = directory / "sources"
    sources.mkdir()
    # A representative server pack contains the paths the real server requires.
    server = pack(sources, "data-001", {
        "static/mst_decoded/F_UNIT_MST.ndjson": b"unit\n",
        "static/mst_decoded/F_MISSION_MST.ndjson": b"mission\n",
        "static/client/shared_prefs/gamedata.xml": b"<game/>\n",
        "static/text_decoded/english.ndjson": b"translation\n",
        "native/mst/Ver001_test.dat": b"mst\n",
        "native/localized_texts/en/Ver001_test.dat": b"localized\n",
        "native/en/sd/area/Ver461_spdungeon1.cpk": b"cpk\n",
        "native/common_lang/sd/gacha/Ver2_test.cpk": b"common\n",
        "native/en/sd/area/Ver462_optional.cpk": b"extra\n",
    })
    client = pack(sources, "client-assets", {
        offline_data.ASSET_FILE: b"fake bundled client assets\n"
    })
    manifest = {
        "schema": 1,
        "version": "offline-data-test",
        "revision": 1,
        "packs": [client, server],
        "installedBytes": 1024,
        "files": 10,
    }
    path = directory / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return data, path, manifest


class OfflineDataTests(unittest.TestCase):
    def test_full_first_install_and_offline_reverify(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, path, manifest = fixture(Path(tmp))
            self.assertEqual(offline_data.main(["plan", "--data", str(data), "--manifest", str(path)]), 0)
            self.assertEqual(offline_data.main(["install", "--data", str(data), "--manifest", str(path)]), 0)
            self.assertEqual(offline_data.main(["verify", "--data", str(data), "--manifest", str(path)]), 0)
            self.assertEqual(len(offline_data.read_json(data / "installed.json")), 2)
            self.assertEqual((data / offline_data.ASSET_FILE).read_bytes(), b"fake bundled client assets\n")
            self.assertEqual(offline_data.plan(manifest, data), ([], None))
            # A second installation and verification cannot require network.
            with patch.object(offline_data.fetch_data, "download", side_effect=AssertionError("unexpected network")):
                self.assertEqual(offline_data.main(["install", "--data", str(data), "--manifest", str(path)]), 0)
                self.assertEqual(offline_data.main(["verify", "--data", str(data), "--manifest", str(path)]), 0)

    def test_revision_10_appends_only_summon_art_without_reinstalling_old_packs(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, path, manifest = fixture(Path(tmp))
            self.assertEqual(offline_data.main(["install", "--data", str(data), "--manifest", str(path)]), 0)
            asset = data / offline_data.ASSET_FILE
            asset_mtime = asset.stat().st_mtime_ns
            native = data / "native/mst/Ver001_test.dat"
            native_mtime = native.stat().st_mtime_ns
            saved = data / "save.json"
            saved.write_text('{"progress": 42}')
            extra = pack(Path(tmp) / "sources", "summon-art", {
                "static/summon-art/example.png": b"demo art"
            })
            manifest["revision"] = 10
            manifest["packs"].append(extra)
            self.assertEqual([pack["id"] for pack in offline_data.plan(manifest, data)[0]],
                             ["summon-art"])
            self.assertIsNone(offline_data.plan(manifest, data)[1])
            self.assertEqual(asset.stat().st_mtime_ns, asset_mtime)
            self.assertEqual(native.stat().st_mtime_ns, native_mtime)
            self.assertEqual(saved.read_text(), '{"progress": 42}')
            self.assertIn("pack not installed/current: summon-art",
                          offline_data.verify(manifest, data))

    def test_client_asset_damage_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, path, manifest = fixture(Path(tmp))
            self.assertEqual(offline_data.main(["install", "--data", str(data), "--manifest", str(path)]), 0)
            (data / offline_data.ASSET_FILE).write_bytes(b"damaged")
            self.assertEqual(offline_data.main(["verify", "--data", str(data), "--manifest", str(path)]), 1)

    def test_corrupt_client_assets_repaired_without_server_redownload(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, path, manifest = fixture(Path(tmp))
            self.assertEqual(offline_data.main(["install", "--data", str(data), "--manifest", str(path)]), 0)
            server_file = data / "native/mst/Ver001_test.dat"
            stamp = server_file.stat().st_mtime_ns
            (data / offline_data.ASSET_FILE).write_bytes(b"corrupted")
            self.assertEqual(offline_data.main(["install", "--data", str(data), "--manifest", str(path)]), 0)
            self.assertEqual((data / offline_data.ASSET_FILE).read_bytes(), b"fake bundled client assets\n")
            self.assertEqual(server_file.stat().st_mtime_ns, stamp)

    def test_missing_large_resource_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, path, manifest = fixture(Path(tmp))
            self.assertEqual(offline_data.main(["install", "--data", str(data), "--manifest", str(path)]), 0)
            (data / "native/en/sd/area/Ver461_spdungeon1.cpk").unlink()
            self.assertEqual(offline_data.main(["verify", "--data", str(data), "--manifest", str(path)]), 1)

    def test_client_assets_update_does_not_redownload_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, path, manifest = fixture(Path(tmp))
            self.assertEqual(offline_data.main(["install", "--data", str(data), "--manifest", str(path)]), 0)
            saved = (data / "native/mst/Ver001_test.dat").stat().st_mtime_ns
            client_new = pack(Path(tmp) / "sources", "client-assets-v2", {
                offline_data.ASSET_FILE: b"v2 client assets\n",
            })
            client_new["id"] = "client-assets"
            manifest["packs"][0] = client_new
            path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(offline_data.main(["install", "--data", str(data), "--manifest", str(path)]), 0)
            self.assertEqual((data / offline_data.ASSET_FILE).read_bytes(), b"v2 client assets\n")
            self.assertEqual((data / "native/mst/Ver001_test.dat").stat().st_mtime_ns, saved)

    def test_manifest_file_count_catches_a_noncritical_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, path, manifest = fixture(Path(tmp))
            self.assertEqual(offline_data.main(["install", "--data", str(data), "--manifest", str(path)]), 0)
            (data / "native/en/sd/area/Ver462_optional.cpk").unlink()
            self.assertIn("incomplete file inventory: 9 / 10", offline_data.verify(manifest, data))

    def test_reject_unsafe_client_zip_without_overwriting_any_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, path, manifest = fixture(Path(tmp))
            pack_new = pack(Path(tmp) / "sources", "client-bad", {
                "../../untrusted": b"bad",
                offline_data.ASSET_FILE: b"assets",
            })
            pack_new["id"] = "client-assets"
            manifest["packs"][0] = pack_new
            path.write_text(json.dumps(manifest), encoding="utf-8")
            data.mkdir(parents=True)
            state = data / "user-save.txt"
            state.write_text("existing campaign", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unexpected client-assets layout"):
                offline_data.main(["install", "--data", str(data), "--manifest", str(path)])
            self.assertEqual(state.read_text(), "existing campaign")
            self.assertFalse((Path(tmp) / "untrusted").exists())
            self.assertNotIn("client-assets", offline_data.read_json(data / "installed.json"))

    def test_android_private_game_files_are_shared_not_copied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unused, path, manifest = fixture(root)
            client_files = root / "app-private" / "files"
            data = client_files / "exvius" / "data"
            arguments = ["--data", str(data), "--manifest", str(path),
                         "--android-files", str(client_files)]
            self.assertEqual(offline_data.main(["install", *arguments]), 0)
            self.assertEqual(offline_data.main(["verify", *arguments]), 0)
            self.assertTrue((data / "native").is_dir())
            self.assertFalse((data / "native").is_symlink())
            self.assertEqual(
                sorted(p.name for p in (data / "native").iterdir()),
                sorted(offline_data.fetch_data.NATIVE_TOPS),
            )
            for name in offline_data.fetch_data.NATIVE_TOPS:
                self.assertTrue((data / "native" / name).is_symlink())
                self.assertEqual((data / "native" / name).resolve(), client_files / name)
            # The server's CDN_ROOT cannot browse exvius/data, saves or other
            # app-private files through the native resource directory.
            self.assertFalse((data / "native/exvius").exists())
            self.assertTrue((client_files / "en/sd/area/Ver461_spdungeon1.cpk").is_file())
            self.assertTrue((data / offline_data.ASSET_FILE).is_file())
            self.assertTrue((data / "native/en/sd/area/Ver461_spdungeon1.cpk").samefile(
                client_files / "en/sd/area/Ver461_spdungeon1.cpk"
            ))
            self.assertEqual(offline_data.verify(manifest, data), [])

    def test_android_layout_never_replaces_existing_native_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client_files = root / "files"
            data = client_files / "exvius/data"
            native = data / "native"
            native.mkdir(parents=True)
            existing = native / "keep-this.txt"
            existing.write_text("preserve user files")
            with self.assertRaisesRegex(ValueError, "Refusing unexpected native entries"):
                offline_data.android_files_layout(data, client_files, create=True)
            self.assertEqual(existing.read_text(), "preserve user files")

    def test_android_layout_rejects_link_to_private_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = root / "files"
            data = files / "exvius/data"
            data.mkdir(parents=True)
            (data / "native").symlink_to("../..", target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "unsafe native root"):
                offline_data.android_files_layout(data, files, create=True)

    def test_android_layout_refuses_resource_symlink_outside_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = root / "app/files"
            files.mkdir(parents=True)
            outside = root / "other-data"
            outside.mkdir()
            (files / "mst").symlink_to(outside, target_is_directory=True)
            data = files / "exvius/data"
            with self.assertRaisesRegex(ValueError, "Refusing unsafe game resource path"):
                offline_data.android_files_layout(data, files, create=True)
            self.assertFalse((data / "native").exists())

    def test_android_layout_rejects_path_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wrong = root / "wrong"
            with self.assertRaisesRegex(ValueError, "Expected --data"):
                offline_data.android_files_layout(wrong, root / "app/files", create=True)
            self.assertFalse(wrong.exists())

    def test_storage_guard_stops_download_before_mutating_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, path, manifest = fixture(Path(tmp))
            from collections import namedtuple
            Disk = namedtuple("Disk", "total used free")
            with patch.object(offline_data.shutil, "disk_usage", return_value=Disk(100, 99, 1)):
                self.assertEqual(offline_data.main(["install", "--data", str(data), "--manifest", str(path)]), 2)
            self.assertFalse(data.exists())

    def test_duplicate_pack_ids_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, path, manifest = fixture(Path(tmp))
            manifest["packs"].append(dict(manifest["packs"][0]))
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate pack ID"):
                offline_data.main(["plan", "--data", str(data), "--manifest", str(path)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
