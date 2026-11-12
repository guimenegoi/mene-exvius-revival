#!/usr/bin/env python3
"""Minimal, source-only transport patch for the user's original FFBE Global 9.1.0 APK.

No APK, DEX, proprietary resource or signing key is included in this repository.
This is a development probe, NOT a standalone/offline-ready game package.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

ORIGINAL_BASE_SHA256 = "0c0edf056e564e689d6fb5d95832d66a06611034045e256c51779b0418bf3735"
CLASS = "Lcom/mene/exvius/LocalTransport;"
TARGETS = (
    (
        "smali_classes3/org/cocos2dx/lib/Cocos2dxHttpURLConnection.smali",
        ".method static createHttpURLConnection(Ljava/lang/String;)Ljava/net/HttpURLConnection;",
        "p0",
    ),
    (
        "smali_classes3/org/cocos2dx/lib/Cocos2dxDownloader.smali",
        ".method public static createTask(Lorg/cocos2dx/lib/Cocos2dxDownloader;ILjava/lang/String;Ljava/lang/String;)V",
        "p2",
    ),
    (
        "smali/com/criware/filesystem/CriFsWebInstaller.smali",
        ".method public Copy(Ljava/lang/String;Ljava/lang/String;)V",
        "p1",
    ),
    (
        "smali/com/square_enix/android_googleplay/FFBEWW/FileDownloader.smali",
        ".method public static downloadFile(JLjava/lang/String;Ljava/lang/String;)V",
        "p2",
    ),
)
HELPER = "smali_classes3/com/mene/exvius/LocalTransport.smali"


def network_helper(port: int) -> str:
    """No DNS, no external proxy: host-only allowlist and original encoded path/query."""
    if not 1024 <= port <= 65535:
        raise ValueError("Unprivileged localhost port must be within 1024..65535")
    return (
        """.class public final Lcom/mene/exvius/LocalTransport;
.super Ljava/lang/Object;

# URL redirection applies ONLY to FFBE-owned domains, not third-party URLs.
# java.net.URL parsing does not make a network request.
.method public static rewrite(Ljava/lang/String;)Ljava/lang/String;
    .locals 4
    if-eqz p0, :original

    :try_start_0
    new-instance v0, Ljava/net/URL;
    invoke-direct {v0, p0}, Ljava/net/URL;-><init>(Ljava/lang/String;)V
    invoke-virtual {v0}, Ljava/net/URL;->getProtocol()Ljava/lang/String;
    move-result-object v1
    const-string v2, "https"
    invoke-virtual {v2, v1}, Ljava/lang/String;->equalsIgnoreCase(Ljava/lang/String;)Z
    move-result v3
    if-nez v3, :host
    const-string v2, "http"
    invoke-virtual {v2, v1}, Ljava/lang/String;->equalsIgnoreCase(Ljava/lang/String;)Z
    move-result v3
    if-eqz v3, :original

    :host
    invoke-virtual {v0}, Ljava/net/URL;->getHost()Ljava/lang/String;
    move-result-object v1
    if-eqz v1, :original
    sget-object v2, Ljava/util/Locale;->ROOT:Ljava/util/Locale;
    invoke-virtual {v1, v2}, Ljava/lang/String;->toLowerCase(Ljava/util/Locale;)Ljava/lang/String;
    move-result-object v1

    const-string v2, "gumi.sg"
    invoke-virtual {v1, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v3
    if-nez v3, :local
    const-string v2, ".gumi.sg"
    invoke-virtual {v1, v2}, Ljava/lang/String;->endsWith(Ljava/lang/String;)Z
    move-result v3
    if-nez v3, :local
    const-string v2, "exvius.com"
    invoke-virtual {v1, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v3
    if-nez v3, :local
    const-string v2, ".exvius.com"
    invoke-virtual {v1, v2}, Ljava/lang/String;->endsWith(Ljava/lang/String;)Z
    move-result v3
    if-eqz v3, :original

    :local
    new-instance v1, Ljava/lang/StringBuilder;
    const-string v2, "http://127.0.0.1:PORT"
    invoke-direct {v1, v2}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V
    invoke-virtual {v0}, Ljava/net/URL;->getFile()Ljava/lang/String;
    move-result-object v2
    invoke-virtual {v1, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {v1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;
    move-result-object v1
    return-object v1
    :try_end_0
    .catch Ljava/lang/Exception; {:try_start_0 .. :try_end_0} :caught

    :caught
    move-exception v0
    :original
    return-object p0
.end method
"""
    ).replace("127.0.0.1:PORT", f"127.0.0.1:{port}")


def prepare(decoded: Path, port: int = 18080) -> list[Path]:
    """Preflight all patches before modifying any file; reject unknown layouts."""
    changes: dict[Path, str] = {}
    for relative, signature, url_register in TARGETS:
        path = decoded / relative
        content = path.read_text(encoding="utf-8")
        method = re.compile(
            rf"(?ms)^{re.escape(signature)}\n.*?^\.end method$"
        )
        matches = list(method.finditer(content))
        if len(matches) != 1:
            raise ValueError(f"Expected one matching method in {relative}, got {len(matches)}")
        original = matches[0].group()
        if CLASS in original:
            raise ValueError(f"Already patched: {relative}")
        insertion = (
            f"    invoke-static {{{url_register}}}, {CLASS}"
            "->rewrite(Ljava/lang/String;)Ljava/lang/String;\n"
            f"    move-result-object {url_register}\n"
        )
        body, n = re.subn(
            r"(?m)^    \.locals [0-9]+\n",
            lambda m: m.group() + "\n" + insertion,
            original,
            count=1,
        )
        if n != 1:
            raise ValueError(f"Register declaration not found: {relative}")
        changes[path] = content[:matches[0].start()] + body + content[matches[0].end():]

    helper = decoded / HELPER
    if helper.exists():
        raise ValueError(f"Refusing to overwrite existing helper: {helper}")
    changes[helper] = network_helper(port)

    for path, content in changes.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return list(changes)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", required=True, type=Path, help="Original APK base 9.1.0")
    parser.add_argument("--decoded", required=True, type=Path, help="Apktool 3.0.3 decoded directory")
    parser.add_argument("--port", type=int, default=18080)
    args = parser.parse_args()
    digest = hashlib.sha256(args.apk.read_bytes()).hexdigest()
    if digest != ORIGINAL_BASE_SHA256:
        parser.error("APK hash mismatch: only the verified original Global 9.1.0 is supported")
    if not (args.decoded / "apktool.yml").is_file():
        parser.error("Decoded apktool directory not found")
    files = prepare(args.decoded, args.port)
    print("Patched 4 original Java entrypoints + 1 allowlisted helper:")
    for path in files:
        print("  " + str(path.relative_to(args.decoded)))
    print("NOTE: Dev-only transport test. Server embedding and offline APK are NOT implemented.")


if __name__ == "__main__":
    main()
