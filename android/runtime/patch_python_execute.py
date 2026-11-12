#!/usr/bin/env python3
"""Dev-only: extend verified native load probe to execute embedded Python.

Apply after patch_transport, patch_bootstrap_probe and patch_python_probe.
The game activity is hooked AFTER its superclass onCreate for a valid Context.
Does not start the FFBE backend or change any game behavior.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

from patch_bootstrap_probe import ORIGINAL_BASE_SHA256, LAPIS, SUPER_CREATE
from patch_python_probe import PROBE_PATH, PROBE_CLASS

METHODS = r"""
.method public static native execute(Landroid/content/Context;)Ljava/lang/String;
.end method

.method public static runDemo(Landroid/content/Context;)V
    .locals 3
    :try_start
    invoke-static {p0}, Lcom/mene/exvius/LocalPythonProbe;->execute(Landroid/content/Context;)Ljava/lang/String;
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


def patch_lapis(content: str) -> str:
    signature = ".method protected onCreate(Landroid/os/Bundle;)V"
    matches = list(re.finditer(
        r"(?ms)^" + re.escape(signature) + r"\n.*?^\.end method$", content,
    ))
    if len(matches) != 1:
        raise ValueError("Unknown FFBE Lapis.onCreate body")
    match = matches[0]
    old = match.group()
    if old.count(SUPER_CREATE) != 1 or old.count("Lcom/mene/exvius/LocalBootstrap;->start()V") != 1:
        raise ValueError("Previously verified bootstrap missing")
    if PROBE_CLASS in old:
        raise ValueError("Native Python execute probe already installed")
    injection = (
        "\n    invoke-static {p0}, "
        + PROBE_CLASS + "->runDemo(Landroid/content/Context;)V\n"
    )
    updated = old.replace(SUPER_CREATE, SUPER_CREATE + injection, 1)
    return content[:match.start()] + updated + content[match.end():]


def prepare(decoded: Path) -> list[Path]:
    if not (decoded / "apktool.yml").is_file():
        raise ValueError("Missing apktool.yml")
    lapis = decoded / LAPIS
    helper = decoded / PROBE_PATH
    if not lapis.is_file() or not helper.is_file():
        raise ValueError("Apply proven native Python version probe first")
    previous = helper.read_text(encoding="utf-8")
    if previous.count(".method public static native version()Ljava/lang/String;") != 1:
        raise ValueError("Expected version-only helper")
    if "runDemo(" in previous or " native execute(" in previous:
        raise ValueError("Already patched Python execution probe")
    patched = patch_lapis(lapis.read_text(encoding="utf-8"))
    lapis.write_text(patched, encoding="utf-8")
    helper.write_text(previous + METHODS, encoding="utf-8")
    return [lapis, helper]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--decoded", type=Path, required=True)
    args = parser.parse_args()
    if hashlib.sha256(args.apk.read_bytes()).hexdigest() != ORIGINAL_BASE_SHA256:
        parser.error("Only pinned FFBE Global 9.1.0 original APK supported")
    for path in prepare(args.decoded):
        print(path.relative_to(args.decoded))
    print("LAB ONLY: execute 6*7 in Python, without Revival backend or data.")


if __name__ == "__main__":
    main()
