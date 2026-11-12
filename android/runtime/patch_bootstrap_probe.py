#!/usr/bin/env python3
"""Development-only probe: prove an in-process Android loopback lifecycle.

This script is NOT a Python runtime, offline backend, or playable APK.
Apply after android/network/patch_transport.py to the user's pinned FFBE 9.1.0
base APK decoded by apktool. No proprietary files are committed.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

ORIGINAL_BASE_SHA256 = "0c0edf056e564e689d6fb5d95832d66a06611034045e256c51779b0418bf3735"
LAPIS = "smali/com/square_enix/android_googleplay/FFBEWW/Lapis.smali"
BOOTSTRAP_PATH = "smali_classes3/com/mene/exvius/LocalBootstrap.smali"
WORKER_PATH = "smali_classes3/com/mene/exvius/LocalBootstrap$Worker.smali"
BOOTSTRAP_CLASS = "Lcom/mene/exvius/LocalBootstrap;"
ON_CREATE = ".method protected onCreate(Landroid/os/Bundle;)V"
ON_DESTROY = ".method public onDestroy()V"
SUPER_CREATE = "    invoke-super {p0, p1}, Lorg/cocos2dx/lib/Cocos2dxActivity;->onCreate(Landroid/os/Bundle;)V"
SUPER_DESTROY = "    invoke-super {p0}, Lorg/cocos2dx/lib/Cocos2dxActivity;->onDestroy()V"

BOOTSTRAP = r""".class public final Lcom/mene/exvius/LocalBootstrap;
.super Ljava/lang/Object;

.field private static volatile active:Z
.field private static volatile listener:Ljava/net/ServerSocket;

.method public static start()V
    .locals 3
    sget-boolean v0, Lcom/mene/exvius/LocalBootstrap;->active:Z
    if-nez v0, :done
    const/4 v0, 0x1
    sput-boolean v0, Lcom/mene/exvius/LocalBootstrap;->active:Z
    new-instance v0, Ljava/lang/Thread;
    new-instance v1, Lcom/mene/exvius/LocalBootstrap$Worker;
    invoke-direct {v1}, Lcom/mene/exvius/LocalBootstrap$Worker;-><init>()V
    const-string v2, "FFBE-Local-Probe"
    invoke-direct {v0, v1, v2}, Ljava/lang/Thread;-><init>(Ljava/lang/Runnable;Ljava/lang/String;)V
    const/4 v1, 0x1
    invoke-virtual {v0, v1}, Ljava/lang/Thread;->setDaemon(Z)V
    invoke-virtual {v0}, Ljava/lang/Thread;->start()V
    :done
    return-void
.end method

.method public static stop()V
    .locals 2
    const/4 v1, 0x0
    sput-boolean v1, Lcom/mene/exvius/LocalBootstrap;->active:Z
    sget-object v0, Lcom/mene/exvius/LocalBootstrap;->listener:Ljava/net/ServerSocket;
    if-eqz v0, :done
    :try_close
    invoke-virtual {v0}, Ljava/net/ServerSocket;->close()V
    :try_end
    .catch Ljava/io/IOException; {:try_close .. :try_end} :ignore
    :ignore
    :done
    return-void
.end method

.method public static serve()V
    .locals 7
    :try_start
    const-string v0, "127.0.0.1"
    invoke-static {v0}, Ljava/net/InetAddress;->getByName(Ljava/lang/String;)Ljava/net/InetAddress;
    move-result-object v0
    new-instance v1, Ljava/net/ServerSocket;
    const/16 v2, 0x46a1
    const/4 v3, 0x1
    invoke-direct {v1, v2, v3, v0}, Ljava/net/ServerSocket;-><init>(IILjava/net/InetAddress;)V
    sput-object v1, Lcom/mene/exvius/LocalBootstrap;->listener:Ljava/net/ServerSocket;
    const-string v5, "FFBE-LocalBootstrap"
    const-string v6, "in-app loopback probe listening 127.0.0.1:18081"
    invoke-static {v5, v6}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    :loop
    sget-boolean v2, Lcom/mene/exvius/LocalBootstrap;->active:Z
    if-eqz v2, :close_listener
    invoke-virtual {v1}, Ljava/net/ServerSocket;->accept()Ljava/net/Socket;
    move-result-object v2
    invoke-virtual {v2}, Ljava/net/Socket;->getOutputStream()Ljava/io/OutputStream;
    move-result-object v3
    const-string v4, "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 21\r\nConnection: close\r\n\r\nFFBE-BOOTSTRAP-READY\n"
    const-string v5, "UTF-8"
    invoke-virtual {v4, v5}, Ljava/lang/String;->getBytes(Ljava/lang/String;)[B
    move-result-object v4
    invoke-virtual {v3, v4}, Ljava/io/OutputStream;->write([B)V
    invoke-virtual {v3}, Ljava/io/OutputStream;->flush()V
    invoke-virtual {v2}, Ljava/net/Socket;->close()V
    goto :loop

    :close_listener
    invoke-virtual {v1}, Ljava/net/ServerSocket;->close()V
    :try_end
    .catch Ljava/lang/Exception; {:try_start .. :try_end} :error
    goto :cleanup

    :error
    move-exception v0
    sget-boolean v2, Lcom/mene/exvius/LocalBootstrap;->active:Z
    if-eqz v2, :cleanup
    const-string v2, "FFBE-LocalBootstrap"
    invoke-static {v2, v0}, Landroid/util/Log;->w(Ljava/lang/String;Ljava/lang/Throwable;)I

    :cleanup
    sget-object v0, Lcom/mene/exvius/LocalBootstrap;->listener:Ljava/net/ServerSocket;
    if-eqz v0, :clear
    :try_close
    invoke-virtual {v0}, Ljava/net/ServerSocket;->close()V
    :try_close_end
    .catch Ljava/io/IOException; {:try_close .. :try_close_end} :ignore
    :ignore
    :clear
    const/4 v0, 0x0
    sput-object v0, Lcom/mene/exvius/LocalBootstrap;->listener:Ljava/net/ServerSocket;
    sput-boolean v0, Lcom/mene/exvius/LocalBootstrap;->active:Z
    return-void
.end method
"""

WORKER = r""".class public final Lcom/mene/exvius/LocalBootstrap$Worker;
.super Ljava/lang/Object;
.implements Ljava/lang/Runnable;

.method public constructor <init>()V
    .locals 0
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V
    return-void
.end method

.method public run()V
    .locals 0
    invoke-static {}, Lcom/mene/exvius/LocalBootstrap;->serve()V
    return-void
.end method
"""


def patch_lifecycle(content: str) -> str:
    """Preflight both hooks before touching the decoded APK."""
    patterns = (
        (ON_CREATE, SUPER_CREATE, "start"),
        (ON_DESTROY, SUPER_DESTROY, "stop"),
    )
    planned = []
    for signature, superclass_call, action in patterns:
        matches = list(re.finditer(r"(?ms)^" + re.escape(signature) + r"\n.*?^\.end method$", content))
        if len(matches) != 1:
            raise ValueError(f"Unknown Lapis lifecycle layout: {signature}")
        match = matches[0]
        old = match.group()
        if BOOTSTRAP_CLASS in old or old.count(superclass_call) != 1:
            raise ValueError(f"Unexpected or already patched lifecycle: {signature}")
        hook = f"    invoke-static {{}}, {BOOTSTRAP_CLASS}->{action}()V"
        replacement = old.replace(superclass_call, hook + "\n\n" + superclass_call, 1)
        planned.append((match.start(), match.end(), replacement))
    for start, end, replacement in reversed(planned):
        content = content[:start] + replacement + content[end:]
    return content


def prepare(decoded: Path) -> list[Path]:
    if not (decoded / "apktool.yml").is_file():
        raise ValueError("Missing apktool.yml; expected an apktool decoded APK")
    # Reuse the existing proven four Java transport call sites, not a new proxy.
    if not (decoded / "smali_classes3/com/mene/exvius/LocalTransport.smali").is_file():
        raise ValueError("Apply the existing transport patch before the lifecycle probe")
    destinations = [decoded / LAPIS, decoded / BOOTSTRAP_PATH, decoded / WORKER_PATH]
    if any(path.exists() for path in destinations[1:]):
        raise ValueError("Bootstrap helper already exists; refusing double patch")
    patched = patch_lifecycle(destinations[0].read_text(encoding="utf-8"))
    # No writes occur until all layout/duplication checks have completed.
    destinations[0].write_text(patched, encoding="utf-8")
    destinations[1].parent.mkdir(parents=True, exist_ok=True)
    destinations[1].write_text(BOOTSTRAP, encoding="utf-8")
    destinations[2].write_text(WORKER, encoding="utf-8")
    return destinations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--decoded", required=True, type=Path)
    args = parser.parse_args()
    digest = hashlib.sha256(args.apk.read_bytes()).hexdigest()
    if digest != ORIGINAL_BASE_SHA256:
        parser.error("Original APK hash mismatch; only pinned Global 9.1.0 supported")
    for path in prepare(args.decoded):
        print(path.relative_to(args.decoded))
    print("DEV PROBE ONLY: loopback health listener on 127.0.0.1:18081.")
    print("This does not integrate Python, game resources, saves, or offline gameplay.")


if __name__ == "__main__":
    main()
