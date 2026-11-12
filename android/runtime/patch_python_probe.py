#!/usr/bin/env python3
"""Development-only native libpython load probe for the pinned FFBE Global 9.1.0.

Apply after patch_transport.py and patch_bootstrap_probe.py to a decoded APK.
This only calls Py_GetVersion() and logs the result; it is NOT a Python runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

from patch_bootstrap_probe import ORIGINAL_BASE_SHA256, BOOTSTRAP_PATH

PROBE_PATH = "smali_classes3/com/mene/exvius/LocalPythonProbe.smali"
PROBE_CLASS = "Lcom/mene/exvius/LocalPythonProbe;"

PROBE = r""".class public final Lcom/mene/exvius/LocalPythonProbe;
.super Ljava/lang/Object;

.method public static native version()Ljava/lang/String;
.end method

.method public static probe()V
    .locals 3
    :try_start
    const-string v0, "python3.14"
    invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V
    const-string v0, "ffbe_python_probe"
    invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V
    invoke-static {}, Lcom/mene/exvius/LocalPythonProbe;->version()Ljava/lang/String;
    move-result-object v1
    const-string v0, "FFBE-EmbeddedPython"
    invoke-static {v0, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I
    :try_end
    .catch Ljava/lang/Throwable; {:try_start .. :try_end} :error
    return-void

    :error
    move-exception v1
    const-string v0, "FFBE-EmbeddedPython"
    invoke-static {v0, v1}, Landroid/util/Log;->w(Ljava/lang/String;Ljava/lang/Throwable;)I
    return-void
.end method
"""


def patch_bootstrap(content: str) -> str:
    """Require the current proven bootstrap, not arbitrary client code."""
    signature = ".method public static start()V"
    matches = list(re.finditer(
        r"(?ms)^" + re.escape(signature) + r"\n.*?^\.end method$", content,
    ))
    if len(matches) != 1:
        raise ValueError("Unexpected LocalBootstrap.start method")
    match = matches[0]
    old = match.group()
    if PROBE_CLASS in old:
        raise ValueError("Already patched native Python probe")
    local = "    .locals 3\n"
    if old.count(local) != 1 or "FFBE-Local-Probe" not in old:
        raise ValueError("Unknown LocalBootstrap method body")
    injected = (
        "    invoke-static {}, "
        + PROBE_CLASS + "->probe()V\n"
    )
    new = old.replace(local, local + injected, 1)
    return content[:match.start()] + new + content[match.end():]


def prepare(decoded: Path) -> list[Path]:
    if not (decoded / "apktool.yml").is_file():
        raise ValueError("Missing apktool.yml")
    helper = decoded / BOOTSTRAP_PATH
    probe = decoded / PROBE_PATH
    if not helper.is_file() or not (
        decoded / "smali_classes3/com/mene/exvius/LocalTransport.smali"
    ).is_file():
        raise ValueError("Apply existing transport and bootstrap patches first")
    if probe.exists():
        raise ValueError("Native Python probe helper already exists")
    revised = patch_bootstrap(helper.read_text(encoding="utf-8"))
    helper.write_text(revised, encoding="utf-8")
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text(PROBE, encoding="utf-8")
    return [helper, probe]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--decoded", type=Path, required=True)
    args = parser.parse_args()
    if hashlib.sha256(args.apk.read_bytes()).hexdigest() != ORIGINAL_BASE_SHA256:
        parser.error("Only pinned FFBE Global 9.1.0 original base APK is supported")
    for path in prepare(args.decoded):
        print(path.relative_to(args.decoded))
    print("DEV PROBE ONLY: Py_GetVersion inside game, not an initialized interpreter.")


if __name__ == "__main__":
    main()
