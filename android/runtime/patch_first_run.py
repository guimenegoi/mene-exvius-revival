#!/usr/bin/env python3
"""Lab-only: graft the already-built upstream first-run UI onto the pinned FFBE.

The only changed base members are AndroidManifest.xml and the new classes4.dex.
The upstream Java launcher implements DataDownloadActivity, DataUpdates, DataPack,
and GameAssets; no embedded APKs, new network permissions, or game logic changes.
The embedded Python adapter reconciles upstream receipts after data setup.
The launcher waits off-thread for the real Revival HTTP hello with a bounded
failure path; successful 19-pack gameplay is not yet verified.
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from patch_bootstrap_probe import ORIGINAL_BASE_SHA256
from first_run_readiness import patch_smali

UPSTREAM_APK_SHA256 = "98875e7b8ebcd04794b36392f8afa71c207bebeba2f90d939ee9572f034e95e2"
UPSTREAM_INSTALLER_DEX = "classes6.dex"
UPSTREAM_LATEST = "https://raw.githubusercontent.com/Elvlin/exvius-offline/main/data/latest.json"
UPSTREAM_PINNED = "https://raw.githubusercontent.com/Elvlin/exvius-offline/b0b73648ceb1a3783105ed2104600be651c9c515/data/latest.json"
UPSTREAM_UPDATES_SMALI = "smali_classes6/com/exvius/local/DataUpdates.smali"
FIRST_RUN_DEX = "classes4.dex"
MAIN = "com.square_enix.android_googleplay.FFBEWW.Lapis"
INSTALLER = "com.exvius.local.DataDownloadActivity"
ANDROID = "{http://schemas.android.com/apk/res/android}"
LAUNCHER = "android.intent.category.LAUNCHER"
ACTION_MAIN = "android.intent.action.MAIN"
ET.register_namespace("android", "http://schemas.android.com/apk/res/android")


def sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 << 20), b""):
            result.update(block)
    return result.hexdigest()


def pin_manifest_url(source: str) -> str:
    """Lock the three upstream data-manifest lookups to one inspected commit."""
    if source.count(UPSTREAM_LATEST) != 3 or UPSTREAM_PINNED in source:
        raise ValueError("Unrecognized upstream DataUpdates manifest code")
    return source.replace(UPSTREAM_LATEST, UPSTREAM_PINNED)


def patch_manifest(source: bytes) -> bytes:
    root = ET.fromstring(source)
    if root.get("package") != "com.square_enix.android_googleplay.FFBEWW":
        raise ValueError("Expected pinned FFBE Global package")
    application = root.find("application")
    if application is None:
        raise ValueError("Application missing")
    activities = application.findall("activity")
    if any(a.get(ANDROID + "name") == INSTALLER for a in activities):
        raise ValueError("Installer already present in AndroidManifest")
    lapis = [a for a in activities if a.get(ANDROID + "name") == MAIN]
    if len(lapis) != 1:
        raise ValueError("Expected original Lapis Activity")
    launchers = []
    for activity in activities:
        for filt in activity.findall("intent-filter"):
            actions = {x.get(ANDROID + "name") for x in filt.findall("action")}
            categories = {x.get(ANDROID + "name") for x in filt.findall("category")}
            if ACTION_MAIN in actions and LAUNCHER in categories:
                launchers.append((activity, filt))
    if len(launchers) != 1 or launchers[0][0] is not lapis[0]:
        raise ValueError("Original must have exactly one Lapis launcher filter")
    filt = launchers[0][1]
    if (len(list(filt.findall("action"))) != 1 or
            len(list(filt.findall("category"))) != 1 or
            filt.find("data") is not None):
        raise ValueError("Unexpected combined launcher filter")
    lapis[0].remove(filt)
    target = ET.Element("activity", {
        ANDROID + "name": INSTALLER,
        ANDROID + "label": "Exvius Offline",
        ANDROID + "exported": "true",
        ANDROID + "screenOrientation": "portrait",
        ANDROID + "theme": "@android:style/Theme.Material.NoActionBar",
    })
    intent = ET.SubElement(target, "intent-filter")
    ET.SubElement(intent, "action", {ANDROID + "name": ACTION_MAIN})
    ET.SubElement(intent, "category", {ANDROID + "name": LAUNCHER})
    application.append(target)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def merge_apk(base: Path, compiled_manifest: bytes, first_run_dex: bytes,
              out: Path) -> dict[str, int]:
    """Copy every existing APK member byte-for-byte, except binary AXML."""
    if out.exists():
        raise FileExistsError(out)
    if not compiled_manifest.startswith(b"\x03\x00\x08\x00"):
        raise ValueError("Expected compiled Android binary XML")
    if not first_run_dex.startswith(b"dex\n"):
        raise ValueError("Expected verified Android DEX bytes")
    with zipfile.ZipFile(base) as src, zipfile.ZipFile(out, "w", allowZip64=True) as dest:
        names = src.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate original APK members")
        if FIRST_RUN_DEX in names:
            raise ValueError("classes4.dex already in base APK")
        if not {"AndroidManifest.xml", "classes.dex", "classes2.dex", "classes3.dex"}.issubset(names):
            raise ValueError("Expected complete pinned multidex FFBE base")
        for info in src.infolist():
            blob = compiled_manifest if info.filename == "AndroidManifest.xml" else src.read(info)
            dest.writestr(info, blob)
        dex_info = zipfile.ZipInfo(FIRST_RUN_DEX, (2026, 11, 12, 0, 0, 0))
        dex_info.compress_type = zipfile.ZIP_STORED
        dex_info.external_attr = 0o100644 << 16
        dest.writestr(dex_info, first_run_dex)
    with zipfile.ZipFile(base) as original, zipfile.ZipFile(out) as built:
        if set(built.namelist()) != set(original.namelist()) | {FIRST_RUN_DEX}:
            raise ValueError("Unexpected output APK members")
        for name in original.namelist():
            if name != "AndroidManifest.xml" and original.read(name) != built.read(name):
                raise ValueError("Original APK member changed: " + name)
        if built.read("AndroidManifest.xml") != compiled_manifest or built.read(FIRST_RUN_DEX) != first_run_dex:
            raise ValueError("Embedded first-run resources did not match")
    return {"preserved_members": len(names) - 1, "new_dex_bytes": len(first_run_dex)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--original-apk", required=True, type=Path)
    parser.add_argument("--base-apk", required=True, type=Path)
    parser.add_argument("--expected-base-sha", required=True)
    parser.add_argument("--upstream-apk", required=True, type=Path)
    parser.add_argument("--decoded-resources", required=True, type=Path)
    parser.add_argument("--apktool", required=True, type=Path)
    parser.add_argument("--java", required=True, type=Path)
    parser.add_argument("--out-apk", required=True, type=Path)
    args = parser.parse_args()
    if sha256(args.original_apk) != ORIGINAL_BASE_SHA256:
        parser.error("Pinned original FFBE 9.1.0 base mismatch")
    if sha256(args.base_apk) != args.expected_base_sha:
        parser.error("Unapproved experimental base APK")
    if sha256(args.upstream_apk) != UPSTREAM_APK_SHA256:
        parser.error("Unapproved upstream first-run APK")
    with zipfile.ZipFile(args.original_apk) as original, \
            zipfile.ZipFile(args.base_apk) as base, \
            zipfile.ZipFile(args.upstream_apk) as upstream:
        if original.read("AndroidManifest.xml") != base.read("AndroidManifest.xml"):
            parser.error("Base manifest no longer matches the pinned original")
        if FIRST_RUN_DEX in base.namelist():
            parser.error("Base already contains a fourth DEX")
        data = upstream.read(UPSTREAM_INSTALLER_DEX)
        for signature in (b"DataDownloadActivity", b"DataUpdates",
                          b"DataPack", b"GameAssets"):
            if signature not in data:
                parser.error("Upstream installer DEX lacks " + signature.decode())
    manifest = args.decoded_resources / "AndroidManifest.xml"
    metadata = args.decoded_resources / "apktool.yml"
    if not manifest.is_file() or not metadata.is_file():
        parser.error("Supply a full apktool resource decode of the original FFBE")
    with tempfile.TemporaryDirectory() as tmp:
        # Keep the pinned source tree untouched: use a copy of the resource
        # decode for building the manifest, never rewrite approved files.
        scratch = Path(tmp)
        from shutil import copytree
        decoded = scratch / "decoded"
        copytree(args.decoded_resources, decoded)
        original_text = (decoded / "AndroidManifest.xml").read_bytes()
        modified = patch_manifest(original_text)
        (decoded / "AndroidManifest.xml").write_bytes(modified)
        result = scratch / "compiled.apk"
        subprocess.run(
            [str(args.java), "-jar", str(args.apktool), "b",
             "-o", str(result), str(decoded)], check=True,
        )
        with zipfile.ZipFile(result) as built:
            compiled = built.read("AndroidManifest.xml")
        # Recompile ONLY the upstream's existing DEX after pinning its three
        # URLs to the manifest revision used by this server, so downloads
        # cannot silently drift to a future incompatible upstream release.
        upstream_dir = scratch / "upstream"
        subprocess.run(
            [str(args.java), "-jar", str(args.apktool), "d", "-r", "-f",
             "-o", str(upstream_dir), str(args.upstream_apk)], check=True,
        )
        updates = upstream_dir / UPSTREAM_UPDATES_SMALI
        updates.write_text(pin_manifest_url(updates.read_text(encoding="utf-8")),
                           encoding="utf-8")
        patch_smali(upstream_dir)
        upstream_rebuilt = scratch / "upstream-compiled.apk"
        subprocess.run(
            [str(args.java), "-jar", str(args.apktool), "b", "-o",
             str(upstream_rebuilt), str(upstream_dir)], check=True,
        )
        with zipfile.ZipFile(upstream_rebuilt) as built:
            data = built.read(UPSTREAM_INSTALLER_DEX)
        if UPSTREAM_PINNED.encode() not in data or UPSTREAM_LATEST.encode() in data:
            raise ValueError("Upstream DEX did not pin the verified data revision")
        for marker in (b"RevivalReadiness", b"/__exvius/hello",
                       b"showReadinessFailure"):
            if marker not in data:
                raise ValueError("Readiness gate missing from rebuilt DEX")
        report = merge_apk(args.base_apk, compiled, data, args.out_apk)
    print(report)
    print("LAB ONLY: upstream launcher waits for verified Revival HTTP hello before Lapis.")


if __name__ == "__main__":
    main()
