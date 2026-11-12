#!/usr/bin/env python3
"""Make an *unpublished* FFBE first-run lab APK reading the private ZIP cache.

Changes ONLY classes4.dex in a pinned unsigned APK. No client game DEX, JNI,
manifest, assets, original libgame.so, signing or saves are changed. The APK
will work for download only while adb reverse + the SSH tunnel are active.
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import tempfile
import zipfile
from pathlib import Path

PINNED_SOURCE = "310bf6167422943c5e28578962db16f747b6936533372825ff2edcc43be96880"
SOURCE_LATEST = "https://raw.githubusercontent.com/Elvlin/exvius-offline/b0b73648ceb1a3783105ed2104600be651c9c515/data/latest.json"
SOURCE_ASSETS = "https://github.com/Elvlin/exvius-offline/releases/download/"
LOCAL_LATEST = "http://127.0.0.1:18082/data/latest.json"
LOCAL_ASSETS = "http://127.0.0.1:18082/packs/"
TARGET_SMALI = "smali_classes4/com/exvius/local/DataUpdates.smali"


def use_resumable_for_manifest(source: str) -> str:
    """Use upstream's existing resumable HTTP client for the small JSON.

    Waydroid's system DownloadManager fails with its generic error on the
    ADB-reversed loopback URL. No change to the real APK: this only removes
    the special small-file branch inside DataUpdates.download(...,label).
    ZIP downloads already use this same HTTP method.
    """
    signature = ".method private static download(Landroid/content/Context;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;JJZLjava/lang/String;)Ljava/io/File;"
    terminator = ".end method"
    if source.count(signature) != 1:
        raise ValueError("Unexpected upstream labelled downloader")
    start = source.index(signature)
    end = source.index(terminator, start) + len(terminator)
    method = source[start:end]
    old = "    if-nez p8, :cond_2"
    if method.count(old) != 1 or method.count("->resumableDownload(") != 1:
        raise ValueError("Unsupported upstream downloader flow")
    if "invoke-static/range {p0 .. p8}" not in method:
        raise ValueError("Missing DownloadManager fallback")
    return source[:start] + method.replace(old, "    nop", 1) + source[end:]


def patch_updates(source: str) -> str:
    if (source.count(SOURCE_LATEST) != 3
            or source.count(SOURCE_ASSETS) != 3
            or LOCAL_LATEST in source or LOCAL_ASSETS in source):
        raise ValueError("Unrecognized or already modified pinned DataUpdates class")
    urls = source.replace(SOURCE_LATEST, LOCAL_LATEST).replace(SOURCE_ASSETS, LOCAL_ASSETS)
    return use_resumable_for_manifest(urls)


def replace_installer_only(source: Path, rebuilt: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(output)
    with zipfile.ZipFile(source) as base, zipfile.ZipFile(rebuilt) as lab:
        members = base.namelist()
        if len(set(members)) != len(members) or "classes4.dex" not in members:
            raise ValueError("Invalid pinned FFBE multidex")
        updated = lab.read("classes4.dex")
        if not updated.startswith(b"dex\n") or LOCAL_LATEST.encode() not in updated:
            raise ValueError("Lab installer DEX was not rebuilt correctly")
        if LOCAL_ASSETS.encode() not in updated:
            raise ValueError("Lab ZIP prefix absent")
        with zipfile.ZipFile(output, "w", allowZip64=True) as destination:
            for info in base.infolist():
                destination.writestr(info, updated if info.filename == "classes4.dex" else base.read(info))
    with zipfile.ZipFile(source) as base, zipfile.ZipFile(output) as built:
        if base.namelist() != built.namelist():
            raise ValueError("APK members changed")
        for name in base.namelist():
            if name != "classes4.dex" and base.read(name) != built.read(name):
                raise ValueError("APK member unexpectedly changed: " + name)
    print("LAB ONLY: original APK members unchanged; classes4.dex uses ADB local ZIP cache")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source-apk", type=Path, required=True)
    parser.add_argument("--out-apk", type=Path, required=True)
    parser.add_argument("--apktool", type=Path, required=True)
    parser.add_argument("--java", type=Path, required=True)
    args = parser.parse_args()
    h = hashlib.sha256()
    with args.source_apk.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != PINNED_SOURCE:
        parser.error("Refusing any APK other than verified Android-native audit build")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        decoded = root / "decoded"
        subprocess.run([
            str(args.java), "-jar", str(args.apktool), "d", "-r", "-f",
            "-o", str(decoded), str(args.source_apk),
        ], check=True)
        target = decoded / TARGET_SMALI
        target.write_text(patch_updates(target.read_text(encoding="utf-8")), encoding="utf-8")
        compiled = root / "compiled.apk"
        subprocess.run([
            str(args.java), "-jar", str(args.apktool), "b",
            "-o", str(compiled), str(decoded),
        ], check=True)
        replace_installer_only(args.source_apk, compiled, args.out_apk)


if __name__ == "__main__":
    main()
