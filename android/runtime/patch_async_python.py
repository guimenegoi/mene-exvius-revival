#!/usr/bin/env python3
"""Lab-only: move already-verified CPython JNI initialization off Lapis.onCreate.

Apply AFTER patch_python_execute.py to the pinned, decoded FFBE 9.1.0 base.
The existing JNI, libs, manifest, transport and game logic are unchanged.
This is not yet a service lifecycle or a readiness-aware game server.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

from patch_bootstrap_probe import ORIGINAL_BASE_SHA256, LAPIS, SUPER_CREATE
from patch_python_probe import PROBE_PATH

WORKER_PATH = "smali_classes3/com/mene/exvius/LocalPythonWorker.smali"
RUN_DEMO = (
    "    invoke-static {p0}, Lcom/mene/exvius/LocalPythonProbe;"
    "->runDemo(Landroid/content/Context;)V"
)
ASYNC_START = (
    "    invoke-static {p0}, Lcom/mene/exvius/LocalPythonProbe;"
    "->startAsync(Landroid/content/Context;)V"
)

# The Android main thread only schedules a single named Java worker.
# The worker retains the application context (not its parent Activity).
# No Android manifest, process service, or additional permissions required.
START_ASYNC_METHOD = r"""
.field private static started:Z

.method public static synchronized startAsync(Landroid/content/Context;)V
    .locals 4
    sget-boolean v0, Lcom/mene/exvius/LocalPythonProbe;->started:Z
    if-eqz v0, :start
    return-void

    :start
    const/4 v0, 0x1
    sput-boolean v0, Lcom/mene/exvius/LocalPythonProbe;->started:Z
    :try_start
    invoke-virtual {p0}, Landroid/content/Context;->getApplicationContext()Landroid/content/Context;
    move-result-object v0
    if-nez v0, :context_ok
    move-object v0, p0

    :context_ok
    new-instance v1, Lcom/mene/exvius/LocalPythonWorker;
    invoke-direct {v1, v0}, Lcom/mene/exvius/LocalPythonWorker;-><init>(Landroid/content/Context;)V
    new-instance v2, Ljava/lang/Thread;
    const-string v3, "FFBE-Python"
    invoke-direct {v2, v1, v3}, Ljava/lang/Thread;-><init>(Ljava/lang/Runnable;Ljava/lang/String;)V
    invoke-virtual {v2}, Ljava/lang/Thread;->start()V
    :try_end
    .catch Ljava/lang/Throwable; {:try_start .. :try_end} :start_failed
    return-void

    :start_failed
    move-exception v0
    const/4 v1, 0x0
    sput-boolean v1, Lcom/mene/exvius/LocalPythonProbe;->started:Z
    const-string v1, "FFBE-EmbeddedPython"
    invoke-static {v1, v0}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/Throwable;)I
    return-void
.end method
"""

WORKER_CLASS = r""".class public final Lcom/mene/exvius/LocalPythonWorker;
.super Ljava/lang/Object;
.implements Ljava/lang/Runnable;

.field private final context:Landroid/content/Context;

.method public constructor <init>(Landroid/content/Context;)V
    .locals 0
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V
    iput-object p1, p0, Lcom/mene/exvius/LocalPythonWorker;->context:Landroid/content/Context;
    return-void
.end method

.method public run()V
    .locals 2
    const-string v0, "FFBE-EmbeddedPython"
    const-string v1, "async worker started"
    invoke-static {v0, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I
    iget-object v0, p0, Lcom/mene/exvius/LocalPythonWorker;->context:Landroid/content/Context;
    invoke-static {v0}, Lcom/mene/exvius/LocalPythonProbe;->runDemo(Landroid/content/Context;)V
    return-void
.end method
"""


def modify_activity(content: str) -> str:
    signature = ".method protected onCreate(Landroid/os/Bundle;)V"
    methods = list(re.finditer(
        r"(?ms)^" + re.escape(signature) + r"\n.*?^\.end method$", content,
    ))
    if len(methods) != 1:
        raise ValueError("Expected exactly one pinned Lapis.onCreate method")
    block = methods[0].group()
    if (block.count(RUN_DEMO) != 1 or block.count(SUPER_CREATE) != 1
            or block.count("Lcom/mene/exvius/LocalBootstrap;->start()V") != 1):
        raise ValueError("Expected existing synchronous execution hook")
    if block.index(SUPER_CREATE) > block.index(RUN_DEMO):
        raise ValueError("Execution hook was not after Activity super.onCreate")
    if ASYNC_START in block:
        raise ValueError("Async hook already installed")
    return content[:methods[0].start()] + block.replace(
        RUN_DEMO, ASYNC_START, 1
    ) + content[methods[0].end():]


def prepare(decoded: Path) -> list[Path]:
    if not (decoded / "apktool.yml").is_file():
        raise ValueError("Missing decoded APK metadata")
    activity = decoded / LAPIS
    probe = decoded / PROBE_PATH
    worker = decoded / WORKER_PATH
    if not activity.is_file() or not probe.is_file() or worker.exists():
        raise ValueError("Expected previously patched client without async worker")
    original_activity = activity.read_text(encoding="utf-8")
    original_probe = probe.read_text(encoding="utf-8")
    if original_probe.count(".method public static runDemo(") != 1:
        raise ValueError("Previously verified JNI execution helper missing")
    if (original_probe.count(".method public static native execute(") != 1
            or "startAsync(" in original_probe or ".field private static started:Z" in original_probe):
        raise ValueError("Unexpected native helper contents")
    changed_activity = modify_activity(original_activity)
    changed_probe = original_probe + START_ASYNC_METHOD
    if worker.parent != probe.parent:
        raise ValueError("Unexpected worker package/dex location")
    # All structural/duplicate guards above run before the first write.
    activity.write_text(changed_activity, encoding="utf-8")
    probe.write_text(changed_probe, encoding="utf-8")
    worker.write_text(WORKER_CLASS, encoding="utf-8")
    return [activity, probe, worker]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--decoded", type=Path, required=True)
    args = parser.parse_args()
    if hashlib.sha256(args.apk.read_bytes()).hexdigest() != ORIGINAL_BASE_SHA256:
        parser.error("Expected pinned original FFBE 9.1.0 base APK")
    for path in prepare(args.decoded):
        print(path.relative_to(args.decoded))
    print("LAB ONLY: embedded Python starts on FFBE-Python Java thread; no game server.")


if __name__ == "__main__":
    main()
