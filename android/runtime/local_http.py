"""Guarded, loopback-only adapter for the *real* Revival handler in Android.

No dummy handler: startup is refused until the 19 verified resource packs
and the client-native data layout are present. The embedded Java worker calls
run() only when preflight() says the private installation is ready.

This is still a lab integration, not a lifecycle-complete Android service.
"""
from __future__ import annotations

import errno
import hashlib
import importlib
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

DATA_MANIFEST = "ffbe_offline_manifest.json"
PACK_COUNT = 19
PORT = 18080
NATIVE_NAMES = frozenset(("mst", "localized_texts", "common_lang", "en", "homeMarquee"))
REQUIRED_FILES = (
    "static/mst_decoded/F_UNIT_MST.ndjson",
    "static/mst_decoded/F_MISSION_MST.ndjson",
    "static/client/shared_prefs/gamedata.xml",
    "static/client/game-assets.apk",
)
REQUIRED_GROUPS = (
    ("native/mst", "*.dat"),
    ("native/localized_texts/en", "*.dat"),
    ("native/en/sd/area", "*.cpk"),
    ("native/common_lang", "**/*.cpk"),
    ("static/text_decoded", "*"),
)


def embedded_archive() -> Path:
    """Find the same private stdlib.zip already used by the JNI probe."""
    name = str(__file__)
    if ".zip/" in name:
        return Path(name.split(".zip/", 1)[0] + ".zip")
    for entry in sys.path:
        if str(entry).endswith("/stdlib.zip") and Path(entry).is_file():
            return Path(entry)
    raise ValueError("Embedded stdlib.zip path unavailable")


def _read_json(path: Path, *, limit: int = 1 << 20) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("missing or unsafe receipt: " + path.name)
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("invalid receipt JSON: " + path.name)
    return parsed



# This asset is derived from the SHA-256-verified client-assets.zip
# in manifest revision 9 (72 MB uncompressed APK).
EXPECTED_CLIENT_SIZE = 71997144
EXPECTED_CLIENT_PACK_SHA256 = "eb70867cc2a97251f01873d31b87702ca90e5612eb8a2f18257ed74cd7d36224"
EXPECTED_CLIENT_SHA256 = "7791690815938dc4a45b2cfce65b0d7745be0f67c3854c7d020cd424bedf33ac"


def _installed_hashes(receipt: dict) -> dict[str, str]:
    """Accept one canonical pack inventory from either installer version.

    The original Python installer writes {id: sha256}; the already-published
    Android DataUpdates class stores packs [{id, sha256, unpackedSize}].
    Neither representation is rewritten during startup.
    """
    if "packs" not in receipt:
        return receipt
    records = receipt["packs"]
    if not isinstance(records, list) or len(records) != PACK_COUNT:
        raise ValueError("Invalid Android installed pack inventory")
    result = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"Invalid Android installed pack record at index {index}")
        name = record.get("id")
        digest = record.get("sha256")
        if (not isinstance(name, str) or not name or name in result
                or "/" in name or "\\" in name
                or not isinstance(digest, str) or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)
                or not isinstance(record.get("unpackedSize"), int)
                or record["unpackedSize"] <= 0):
            raise ValueError(
                f"Invalid or duplicate Android pack entry at index {index}"
                f" (id={str(name)[:64]!r}, unpackedSize={record.get('unpackedSize')!r})"
            )
        result[name] = digest
    return result


def _manifest(archive: Path) -> dict:
    with zipfile.ZipFile(archive) as zf:
        entry = zf.getinfo(DATA_MANIFEST)
        if entry.file_size > 65536 or entry.compress_type != zipfile.ZIP_STORED:
            raise ValueError("embedded data manifest invalid")
        manifest = json.loads(zf.read(entry))
    if not isinstance(manifest, dict):
        raise ValueError("invalid data manifest")
    packs = manifest.get("packs", [])
    if manifest.get("schema") != 1 or not isinstance(packs, list) or len(packs) != PACK_COUNT:
        raise ValueError("pack manifest not supported")
    return manifest


def reconcile_first_run(archive: Path | None = None,
                        app_files: Path | None = None) -> tuple[bool, str]:
    """Finish the verified upstream install without changing installed.json.

    Only the private five native symlinks and one asset receipt are written.
    There are no writes to saves, and no HTTP server is opened here.
    """
    try:
        archive = Path(archive) if archive is not None else embedded_archive()
        files = Path(app_files) if app_files is not None else archive.parent.parent
        data = files / "exvius/data"
        if (files.is_symlink() or (files / "exvius").is_symlink()
                or data.is_symlink() or (data / "static").is_symlink()
                or (data / "static/client").is_symlink()
                or not data.is_dir()):
            return False, "private data unavailable"
        installed = _read_json(data / "installed.json")
        if "packs" not in installed:
            return False, "Python installer already uses canonical receipts"
        if preflight(archive, files)[0]:
            return False, "upstream inventory already reconciled"
        manifest = _manifest(archive)
        if (installed.get("schema") != manifest["schema"]
                or installed.get("revision") != manifest.get("revision")):
            return False, "upstream revision differs from pinned installer"
        installed_hashes = _installed_hashes(installed)
        if any(not isinstance(pack, dict)
               or installed_hashes.get(pack.get("id")) != pack.get("sha256")
               for pack in manifest["packs"]):
            return False, "not all pinned ZIPs were installed"
        client = next(pack for pack in manifest["packs"]
                      if pack.get("id") == "client-assets")
        if (client.get("unpackedSize") != EXPECTED_CLIENT_SIZE
                or client.get("sha256") != EXPECTED_CLIENT_PACK_SHA256):
            return False, "pinned client ZIP changed"
        asset = data / "static/client/game-assets.apk"
        if (asset.is_symlink() or not asset.is_file()
                or asset.stat().st_size != EXPECTED_CLIENT_SIZE):
            return False, "client resource APK missing or wrong size"
        hashed = hashlib.sha256()
        with asset.open("rb") as stream:
            for part in iter(lambda: stream.read(4 << 20), b""):
                hashed.update(part)
        if hashed.hexdigest() != EXPECTED_CLIENT_SHA256:
            return False, "client asset SHA-256 mismatch"
        target = archive.parent / "engine"
        importlib.import_module("ffbe_engine_bootstrap").install(archive, target)
        for relative in ("ios-server", "android/data"):
            path = target / relative
            if not path.is_dir():
                return False, "bundled installer missing: " + relative
            if str(path) not in sys.path:
                sys.path.insert(0, str(path))
        installer = importlib.import_module("offline_data")
        installer.android_files_layout(data, files, create=True)
        installer.atomic_json(data / "offline-client-assets.json", {
            "archive_sha256": client["sha256"],
            "file": "static/client/game-assets.apk",
            "file_size": EXPECTED_CLIENT_SIZE,
            "file_sha256": EXPECTED_CLIENT_SHA256,
        })
        return True, "Android first-run inventory reconciled"
    except (OSError, ValueError, KeyError, TypeError,
            zipfile.BadZipFile, json.JSONDecodeError, ImportError) as exc:
        return False, f"first-run adapter refused: {type(exc).__name__}: {str(exc)[:180]}"


def preflight(archive: Path | None = None,
              app_files: Path | None = None) -> tuple[bool, str]:
    """Read-only validation. Do not import capture_server or touch saves."""
    try:
        archive = Path(archive) if archive is not None else embedded_archive()
        if not archive.is_file():
            return False, "stdlib missing"
        files = (Path(app_files) if app_files is not None
                 else archive.parent.parent)
        data = files / "exvius/data"
        if ((files / "exvius").is_symlink() or data.is_symlink()
                or (data / "static").is_symlink()
                or (data / "static/client").is_symlink()
                or not data.is_dir()):
            return False, "private data root missing/unsafe"
        manifest = _manifest(archive)
        packs = manifest["packs"]
        ids = set()
        installed = _installed_hashes(_read_json(data / "installed.json"))
        for pack in packs:
            if not isinstance(pack, dict):
                return False, "invalid pack entry"
            identifier, expected = pack.get("id"), pack.get("sha256")
            if (not isinstance(identifier, str) or not identifier
                    or "/" in identifier or "\\" in identifier or identifier in ids
                    or not isinstance(expected, str) or len(expected) != 64
                    or any(c not in "0123456789abcdef" for c in expected)):
                return False, "invalid pack hash/id"
            ids.add(identifier)
            if installed.get(identifier) != expected:
                return False, "pack incomplete: " + identifier
        if "client-assets" not in ids:
            return False, "client assets pack missing"
        asset = data / "static/client/game-assets.apk"
        receipt = _read_json(data / "offline-client-assets.json")
        pack = next(p for p in packs if p["id"] == "client-assets")
        if (receipt.get("archive_sha256") != pack["sha256"]
                or receipt.get("file") != "static/client/game-assets.apk"
                or not isinstance(receipt.get("file_size"), int)
                or receipt["file_size"] <= 0 or asset.is_symlink()
                or not asset.is_file() or asset.stat().st_size != receipt["file_size"]
                or not isinstance(receipt.get("file_sha256"), str)
                or len(receipt["file_sha256"]) != 64):
            return False, "client asset receipt missing/obsolete"
        digest = hashlib.sha256()
        with asset.open("rb") as inp:
            for chunk in iter(lambda: inp.read(4 << 20), b""):
                digest.update(chunk)
        if digest.hexdigest() != receipt["file_sha256"]:
            return False, "client asset hash mismatch"

        for relative in REQUIRED_FILES:
            file = data / relative
            if file.is_symlink() or not file.is_file() or file.stat().st_size == 0:
                return False, "required file missing: " + relative
        native = data / "native"
        if native.is_symlink() or not native.is_dir():
            return False, "native resource layout missing/unsafe"
        if {p.name for p in native.iterdir()} != NATIVE_NAMES:
            return False, "native folder names do not match installer"
        for name in NATIVE_NAMES:
            link = native / name
            if not link.is_symlink() or (files / name).is_symlink() or link.resolve() != (files / name).resolve():
                return False, "native resource link invalid: " + name
        for folder, pattern in REQUIRED_GROUPS:
            path = data / folder
            if not path.is_dir() or not any(
                file.is_file() and file.stat().st_size > 0 for file in path.glob(pattern)
            ):
                return False, "required resource group missing: " + folder
        expected_count = manifest.get("files")
        if not isinstance(expected_count, int) or expected_count < 1:
            return False, "expected inventory invalid"
        # Walk the exact five symlink targets and static tree, avoiding a
        # recursive traversal of the app-private files directory or saves.
        root_counts = {
            name: sum(len(names) for _, _, names in os.walk(files / name))
            for name in sorted(NATIVE_NAMES)
        }
        root_counts["static"] = sum(
            len(names) for _, _, names in os.walk(data / "static")
        )
        root_counts["registry"] = int((data / "registry.json").is_file())
        counted = sum(root_counts.values())
        if counted < expected_count:
            # Gameplay can replace/remove files in the mutable MST and
            # homeMarquee groups. This is a narrowly bounded exception based
            # on pinned revision-9 per-directory counts, only after validating
            # all receipts, required resources, client APK hash and symlinks.
            expected_roots = {
                "common_lang": 5607, "en": 911, "homeMarquee": 9,
                "localized_texts": 157, "mst": 299, "static": 5503,
                "registry": 1,
            }
            other_roots_intact = all(
                root_counts.get(name, 0) >= count
                for name, count in expected_roots.items()
                if name not in ("mst", "homeMarquee")
            )
            mst_missing = max(0, expected_roots["mst"] - root_counts["mst"])
            marquee_missing = max(
                0, expected_roots["homeMarquee"] - root_counts["homeMarquee"]
            )
            if (manifest.get("revision") == 9 and expected_count == 12487
                    and other_roots_intact and mst_missing <= 33
                    and marquee_missing <= 6 and (mst_missing or marquee_missing)):
                return True, (
                    "verified pinned data; mutable runtime groups changed "
                    f"(mst -{mst_missing}, homeMarquee -{marquee_missing})"
                )
            summary = ",".join(
                f"{key}:{root_counts[key]}/{expected_roots[key]}"
                for key in sorted(expected_roots)
                if root_counts.get(key, 0) < expected_roots[key]
            )
            return False, (
                f"file inventory incomplete: {counted}/{expected_count}"
                f" ({summary[:160]})"
            )
        return True, "verified 19-pack private data layout"
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        # Diagnostic detail is required on real devices: a generic ValueError
        # hides a bad Android install receipt and strands the startup screen.
        detail = f"preflight failed: {type(exc).__name__}: {str(exc)[:180]}"
        # JNI stores the earlier reconciliation result in __main__; report
        # it only when startup fails, without changing any validation rule.
        adapter = getattr(sys.modules.get("__main__"), "_first_run_reason", None)
        if isinstance(adapter, str) and adapter:
            detail += "; first-run: " + adapter[:180]
        return False, detail


def preserve_native_mst_for_cdn(files: Path) -> int:
    """Pin native MST content in Revival's existing CDN overlay via hardlinks.

    The game's cache updater can unlink original files/mst entries before
    fetching replacements. The CDN must not lose its only copy at that point.
    Hardlinks share bytes. Android builds that forbid app-private hardlinks
    use atomic copies of only the pinned MST and original Vortex CPK, not
    all 19 resource packs. No network or game save writes are involved.
    """
    def preserve(source_file: Path, target_file: Path) -> None:
        try:
            os.link(source_file, target_file, follow_symlinks=False)
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EPERM, errno.EXDEV):
                raise
            staging = target_file.with_name(target_file.name + ".copying")
            if staging.is_symlink() or (staging.exists() and not staging.is_file()):
                raise ValueError("Unsafe immutable overlay staging path")
            try:
                shutil.copyfile(source_file, staging, follow_symlinks=False)
                if staging.stat().st_size != source_file.stat().st_size:
                    raise ValueError("Incomplete immutable overlay copy")
                with staging.open("rb") as written:
                    os.fsync(written.fileno())
                staging.replace(target_file)
            finally:
                staging.unlink(missing_ok=True)

    source = files / "mst"
    overlay_root = files / "exvius/server-root/overlay"
    target = overlay_root / "mst"
    for folder in (files / "exvius", files / "exvius/server-root",
                   overlay_root, target):
        if folder.is_symlink():
            raise ValueError("CDN overlay path is a symlink")
    if source.is_symlink() or not source.is_dir():
        raise ValueError("native MST cache is unavailable or unsafe")
    target.mkdir(parents=True, exist_ok=True)
    linked = 0
    for current, dirs, names in os.walk(source, followlinks=False):
        current_path = Path(current)
        if any((current_path / name).is_symlink() for name in dirs + names):
            raise ValueError("native MST cache contains symlink")
        dest_dir = target / current_path.relative_to(source)
        if dest_dir.is_symlink():
            raise ValueError("CDN overlay contains symlink directory")
        dest_dir.mkdir(parents=True, exist_ok=True)
        for name in names:
            original = current_path / name
            dest = dest_dir / name
            if not original.is_file() or original.stat().st_size == 0:
                raise ValueError("native MST cache contains invalid file")
            if dest.is_symlink() or (dest.exists() and not dest.is_file()):
                raise ValueError("CDN overlay contains invalid file")
            if not dest.exists():
                preserve(original, dest)
                linked += 1
    for name in ("Ver709_i5QEJpua.dat", "Ver9001_YW9MUm2H.dat"):
        if not (target / name).is_file():
            raise ValueError("CDN overlay lacks pinned MST " + name)
    # Same hardlink mechanism for the original Vortex CPK: never rebuild a
    # generated banner pack on top of another generated banner pack.
    base_pack = files / "en/sd/area/Ver461_spdungeon1.cpk"
    pinned_pack = overlay_root / "en/sd/area/Ver461_spdungeon1.cpk"
    for folder in (overlay_root / "en", overlay_root / "en/sd",
                   overlay_root / "en/sd/area"):
        if folder.is_symlink():
            raise ValueError("CDN overlay pack directory is a symlink")
        folder.mkdir(parents=True, exist_ok=True)
    if pinned_pack.is_symlink() or base_pack.is_symlink():
        raise ValueError("CDN source pack is a symlink")
    if not pinned_pack.exists():
        if not base_pack.is_file() or base_pack.stat().st_size == 0:
            raise ValueError("original Vortex resource pack unavailable")
        preserve(base_pack, pinned_pack)
        linked += 1
    if not pinned_pack.is_file() or pinned_pack.stat().st_size == 0:
        raise ValueError("CDN overlay has an invalid Vortex resource pack")
    return linked


def run(archive: Path | None = None, app_files: Path | None = None,
        port: int = PORT) -> None:
    """Block the dedicated Java/Python worker inside the *real* HTTP handler.

    No listener is opened before the data and engine have been initialized.
    The Android process owns shutdown until the production lifecycle is added.
    """
    archive = Path(archive) if archive is not None else embedded_archive()
    files = Path(app_files) if app_files is not None else archive.parent.parent
    ok, reason = preflight(archive, files)
    if not ok:
        raise RuntimeError("Refusing Revival HTTP: " + reason)
    count = preserve_native_mst_for_cdn(files)
    print(f"FFBE-CDN-MST-OVERLAY: {count} immutable files preserved", flush=True)
    target = archive.parent / "engine"
    # The bootstrap module exists inside the signed stdlib ZIP, not as a
    # separate Android app, and uses the existing SHA-256 installer.
    importlib.import_module("ffbe_engine_bootstrap").install(archive, target)
    for relative in ("vendor", "source/server", "ios-server"):
        path = target / relative
        if not path.is_dir():
            raise RuntimeError("Revival bundle incomplete: " + relative)
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    # This must occur BEFORE importing serve/capture_server: both modules
    # bind data paths and save state at first import. No earlier probe().
    if "capture_server" in sys.modules or "serve" in sys.modules:
        raise RuntimeError("Revival server imported before private data binding")
    os.environ["FFBE_DATA_DIR"] = str(files / "exvius/data")
    os.environ["FFBE_SERVER_ROOT"] = str(files / "exvius/server-root")
    # The native Android client already has its own shipped MST and CPK data.
    # Never advertise the iPhone-only table rewrites/large version offset.
    os.environ["FFBE_ANDROID_EMBEDDED"] = "1"
    os.environ["EXVIUS_TABLE_VERSION_OFFSET"] = "0"
    os.environ["EXVIUS_IOS_HCA"] = "0"
    os.environ["EXVIUS_IOS_HCA_PLAIN"] = "0"
    os.environ["EXVIUS_IOS_DROP_UNVERSIONED"] = "0"
    # These two resource packs are already installed by the Android data
    # installer. The iPhone's first-battle workaround must not trigger them.
    os.environ["EXVIUS_EARLY_RESOURCES"] = ""
    os.environ["EXVIUS_IOS_SOUND_REFETCH"] = ""
    # A local, schema-validated config is applied BEFORE serve/capture_server
    # bind any environment flags. The sync worker never changes a live engine.
    try:
        import config_model
    except ImportError:
        pass  # Existing signed stable APKs don't carry this optional module.
    else:
        report = config_model.apply_on_boot(
            archive.parent / "private-config",
            files / "exvius/server-root/state/replay.json",
        )
        print("FFBE-CONFIG: " + str(report["reason"])
              + "; active=" + str(report["applied"])
              + "; staged=" + str(report["staged"]), flush=True)
    serve = importlib.import_module("serve")
    serve.configure_engine()
    capture = serve.start_engine()
    handler = serve.make_handler(capture, b"", b"")
    if port != PORT:
        raise ValueError("Android server must use the pinned loopback port")
    # Backup is strictly opt-in: the import is absent in the stable build,
    # and an unpaired worker never reads or transmits the campaign save.
    backup = None
    try:
        from ffbe_backup import BackupCoordinator, wrap_handler
    except ImportError:
        pass
    else:
        backup = BackupCoordinator(
            archive.parent / "private-backup",
            files / "exvius/server-root/state",
        )
        try:
            from config_sync import ConfigSync
        except ImportError:
            pass
        else:
            def config_connection():
                return (backup._load(), backup.ca_file) if backup.enabled() else None
            backup.config_sync = ConfigSync(
                archive.parent / "private-config", config_connection)
        handler = wrap_handler(handler, backup)
    server = serve.Server(("127.0.0.1", PORT), handler)
    server.tls = None
    try:
        if backup is not None:
            backup.start()
        print("FFBE-RevivalHTTP: READY 127.0.0.1:18080 (real Revival)", flush=True)
        server.serve_forever()
    finally:
        server.server_close()
        if backup is not None:
            backup.stop()
