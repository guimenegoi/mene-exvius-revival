"""Fail-closed, off-main-thread readiness gate for pinned upstream Android UI.

Reuses LocalPythonProbe.startAsync, DataDownloadActivity's existing status UI,
and the real Revival hello route. Does not add a second server/listener.
"""
from __future__ import annotations

import re

READINESS_PATH = "smali_classes6/com/mene/exvius/RevivalReadiness.smali"
ACTIVITY_PATH = "smali_classes6/com/exvius/local/DataDownloadActivity.smali"
UPDATES_PATH = "smali_classes6/com/exvius/local/DataUpdates.smali"
STALE_READY_FILE = "mst/Ver9001_YW9MUm2H.dat"
PINNED_READY_FILE = "mst/Ver709_i5QEJpua.dat"
PINNED_MST_PACKS = (
    ("data-011", "Ver709_i5QEJpua.dat"),
    ("story-movies-003", "Ver9001_YW9MUm2H.dat"),
)
GATE_METHOD = "Lcom/mene/exvius/RevivalReadiness;->start(Lcom/exvius/local/DataDownloadActivity;Landroid/content/Intent;)V"
START_ACTIVITY = "    invoke-virtual {p0, v0}, Lcom/exvius/local/DataDownloadActivity;->startActivity(Landroid/content/Intent;)V"
FINISH_ACTIVITY = "    invoke-virtual {p0}, Lcom/exvius/local/DataDownloadActivity;->finish()V"
FAILURE_METHOD = r"""
.method public showReadinessFailure(Ljava/lang/String;)V
    .locals 2
    invoke-virtual {p0}, Lcom/exvius/local/DataDownloadActivity;->isFinishing()Z
    move-result v0
    if-nez v0, :done
    invoke-virtual {p0}, Lcom/exvius/local/DataDownloadActivity;->isDestroyed()Z
    move-result v0
    if-nez v0, :done
    iget-object v0, p0, Lcom/exvius/local/DataDownloadActivity;->status:Landroid/widget/TextView;
    invoke-virtual {v0, p1}, Landroid/widget/TextView;->setText(Ljava/lang/CharSequence;)V
    const/16 v1, 0x8
    iget-object v0, p0, Lcom/exvius/local/DataDownloadActivity;->retry:Landroid/widget/Button;
    invoke-virtual {v0, v1}, Landroid/widget/Button;->setVisibility(I)V
    iget-object v0, p0, Lcom/exvius/local/DataDownloadActivity;->progress:Landroid/widget/ProgressBar;
    invoke-virtual {v0, v1}, Landroid/widget/ProgressBar;->setVisibility(I)V
    :done
    return-void
.end method
"""
GATE_ACTIVITY = r"""    iget-boolean v1, p0, Lcom/exvius/local/DataDownloadActivity;->readinessStarted:Z
    if-eqz v1, :begin_wait
    return-void
    :begin_wait
    const/4 v1, 0x1
    iput-boolean v1, p0, Lcom/exvius/local/DataDownloadActivity;->readinessStarted:Z
    invoke-direct {p0}, Lcom/exvius/local/DataDownloadActivity;->showDownloadPage()V
    iget-object v1, p0, Lcom/exvius/local/DataDownloadActivity;->status:Landroid/widget/TextView;
    const-string v2, "Starting the offline game server..."
    invoke-virtual {v1, v2}, Landroid/widget/TextView;->setText(Ljava/lang/CharSequence;)V
    invoke-static {p0, v0}, Lcom/mene/exvius/RevivalReadiness;->start(Lcom/exvius/local/DataDownloadActivity;Landroid/content/Intent;)V
"""

READINESS_CLASS = r""".class public final Lcom/mene/exvius/RevivalReadiness;
.super Ljava/lang/Object;
.implements Ljava/lang/Runnable;
.source "RevivalReadiness.java"

.field private final activity:Lcom/exvius/local/DataDownloadActivity;
.field private final game:Landroid/content/Intent;
.field private ui:Z
.field private ready:Z

.method private constructor <init>(Lcom/exvius/local/DataDownloadActivity;Landroid/content/Intent;)V
    .locals 0
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V
    iput-object p1, p0, Lcom/mene/exvius/RevivalReadiness;->activity:Lcom/exvius/local/DataDownloadActivity;
    iput-object p2, p0, Lcom/mene/exvius/RevivalReadiness;->game:Landroid/content/Intent;
    return-void
.end method

.method public static start(Lcom/exvius/local/DataDownloadActivity;Landroid/content/Intent;)V
    .locals 3
    new-instance v0, Lcom/mene/exvius/RevivalReadiness;
    invoke-direct {v0, p0, p1}, Lcom/mene/exvius/RevivalReadiness;-><init>(Lcom/exvius/local/DataDownloadActivity;Landroid/content/Intent;)V
    new-instance v1, Ljava/lang/Thread;
    const-string v2, "FFBE-Readiness"
    invoke-direct {v1, v0, v2}, Ljava/lang/Thread;-><init>(Ljava/lang/Runnable;Ljava/lang/String;)V
    const/4 v2, 0x1
    invoke-virtual {v1, v2}, Ljava/lang/Thread;->setDaemon(Z)V
    invoke-virtual {v1}, Ljava/lang/Thread;->start()V
    return-void
.end method

.method private static probe()Z
    .locals 8
    :try_start
    new-instance v0, Ljava/net/URL;
    const-string v1, "http://127.0.0.1:18080/__exvius/hello"
    invoke-direct {v0, v1}, Ljava/net/URL;-><init>(Ljava/lang/String;)V
    invoke-virtual {v0}, Ljava/net/URL;->openConnection()Ljava/net/URLConnection;
    move-result-object v0
    check-cast v0, Ljava/net/HttpURLConnection;
    const/16 v1, 0x2ee
    invoke-virtual {v0, v1}, Ljava/net/HttpURLConnection;->setConnectTimeout(I)V
    invoke-virtual {v0, v1}, Ljava/net/HttpURLConnection;->setReadTimeout(I)V
    const/4 v1, 0x0
    invoke-virtual {v0, v1}, Ljava/net/HttpURLConnection;->setInstanceFollowRedirects(Z)V
    invoke-virtual {v0, v1}, Ljava/net/HttpURLConnection;->setUseCaches(Z)V
    invoke-virtual {v0}, Ljava/net/HttpURLConnection;->getResponseCode()I
    move-result v1
    const/16 v2, 0xc8
    if-ne v1, v2, :failed
    invoke-virtual {v0}, Ljava/net/HttpURLConnection;->getContentLength()I
    move-result v1
    if-lez v1, :failed
    const/16 v2, 0x1000
    if-gt v1, v2, :failed
    invoke-virtual {v0}, Ljava/net/HttpURLConnection;->getInputStream()Ljava/io/InputStream;
    move-result-object v1
    const/16 v2, 0x1000
    new-array v2, v2, [B
    invoke-virtual {v1, v2}, Ljava/io/InputStream;->read([B)I
    move-result v3
    invoke-virtual {v1}, Ljava/io/InputStream;->close()V
    invoke-virtual {v0}, Ljava/net/HttpURLConnection;->disconnect()V
    if-lez v3, :not_ready
    new-instance v4, Ljava/lang/String;
    const/4 v5, 0x0
    const-string v6, "UTF-8"
    invoke-direct {v4, v2, v5, v3, v6}, Ljava/lang/String;-><init>([BIILjava/lang/String;)V
    const-string v6, "Reachable. You can open the game."
    invoke-virtual {v4, v6}, Ljava/lang/String;->contains(Ljava/lang/CharSequence;)Z
    move-result v7
    return v7
    :failed
    invoke-virtual {v0}, Ljava/net/HttpURLConnection;->disconnect()V
    :not_ready
    const/4 v0, 0x0
    return v0
    :try_end
    .catch Ljava/lang/Exception; {:try_start .. :try_end} :network_error
    :network_error
    move-exception v0
    const/4 v0, 0x0
    return v0
.end method

.method public run()V
    .locals 5
    iget-boolean v0, p0, Lcom/mene/exvius/RevivalReadiness;->ui:Z
    if-eqz v0, :worker
    iget-object v1, p0, Lcom/mene/exvius/RevivalReadiness;->activity:Lcom/exvius/local/DataDownloadActivity;
    invoke-virtual {v1}, Lcom/exvius/local/DataDownloadActivity;->isFinishing()Z
    move-result v2
    if-nez v2, :end
    invoke-virtual {v1}, Lcom/exvius/local/DataDownloadActivity;->isDestroyed()Z
    move-result v2
    if-nez v2, :end
    iget-boolean v2, p0, Lcom/mene/exvius/RevivalReadiness;->ready:Z
    if-eqz v2, :error
    iget-object v2, p0, Lcom/mene/exvius/RevivalReadiness;->game:Landroid/content/Intent;
    invoke-virtual {v1, v2}, Lcom/exvius/local/DataDownloadActivity;->startActivity(Landroid/content/Intent;)V
    invoke-virtual {v1}, Lcom/exvius/local/DataDownloadActivity;->finish()V
    return-void
    :error
    const-string v2, "The offline server did not start. Fully close and reopen Exvius to retry."
    invoke-virtual {v1, v2}, Lcom/exvius/local/DataDownloadActivity;->showReadinessFailure(Ljava/lang/String;)V
    :end
    return-void

    :worker
    # Lapis is not constructed yet. Reuse its existing native load probe
    # to load libpython3.14 + the JNI bridge before execute() is invoked.
    # Both loads and CPython initialization run off the Activity main thread.
    invoke-static {}, Lcom/mene/exvius/LocalPythonProbe;->probe()V
    iget-object v0, p0, Lcom/mene/exvius/RevivalReadiness;->activity:Lcom/exvius/local/DataDownloadActivity;
    invoke-virtual {v0}, Lcom/exvius/local/DataDownloadActivity;->getApplicationContext()Landroid/content/Context;
    move-result-object v0
    invoke-static {v0}, Lcom/mene/exvius/LocalPythonProbe;->startAsync(Landroid/content/Context;)V
    const/4 v1, 0x0
    :loop
    const/16 v2, 0xf0
    if-ge v1, v2, :completed
    invoke-static {}, Lcom/mene/exvius/RevivalReadiness;->probe()Z
    move-result v0
    if-eqz v0, :sleep
    const/4 v0, 0x1
    iput-boolean v0, p0, Lcom/mene/exvius/RevivalReadiness;->ready:Z
    goto :completed
    :sleep
    const-wide/16 v3, 0x1f4
    :try_start_sleep
    invoke-static {v3, v4}, Ljava/lang/Thread;->sleep(J)V
    :try_end_sleep
    .catch Ljava/lang/InterruptedException; {:try_start_sleep .. :try_end_sleep} :interrupted
    add-int/lit8 v1, v1, 0x1
    goto :loop
    :interrupted
    move-exception v0
    invoke-static {}, Ljava/lang/Thread;->currentThread()Ljava/lang/Thread;
    move-result-object v0
    invoke-virtual {v0}, Ljava/lang/Thread;->interrupt()V
    :completed
    const/4 v0, 0x1
    iput-boolean v0, p0, Lcom/mene/exvius/RevivalReadiness;->ui:Z
    iget-object v0, p0, Lcom/mene/exvius/RevivalReadiness;->activity:Lcom/exvius/local/DataDownloadActivity;
    invoke-virtual {v0, p0}, Lcom/exvius/local/DataDownloadActivity;->runOnUiThread(Ljava/lang/Runnable;)V
    return-void
.end method
"""


def patch_activity(source: str) -> str:
    """Modify only the pinned upstream openGame() and one UI failure method."""
    signature = ".method private openGame(Z)V"
    methods = list(re.finditer(
        r"(?ms)^" + re.escape(signature) + r"\n.*?^\.end method$", source,
    ))
    if len(methods) != 1:
        raise ValueError("Expected exactly one upstream openGame")
    if ".field private readinessStarted:Z" in source or "showReadinessFailure(" in source:
        raise ValueError("Readiness already patched")
    block = methods[0].group()
    if (block.count(START_ACTIVITY) != 1 or block.count(FINISH_ACTIVITY) != 1
            or block.count("Lcom/exvius/local/GameAssets;->attach(") != 1
            or block.count("Lcom/exvius/local/DataUpdates;->checkInBackground(") != 1
            or block.count(".locals 3") != 1
            or block.index("GameAssets;->attach") > block.index(START_ACTIVITY)
            or block.index("checkInBackground") > block.index(START_ACTIVITY)):
        raise ValueError("Unknown upstream Activity launch path")
    old = (START_ACTIVITY + "\n\n    .line 82\n" + FINISH_ACTIVITY)
    if block.count(old) != 1:
        raise ValueError("Expected single guarded startActivity/finish pair")
    patched = block.replace(
        old, GATE_ACTIVITY.rstrip(), 1,
    )
    source = source[:methods[0].start()] + patched + source[methods[0].end():]
    field = ".field private status:Landroid/widget/TextView;"
    if source.count(field) != 1:
        raise ValueError("Unknown upstream Activity fields")
    source = source.replace(field, field + "\n\n.field private readinessStarted:Z", 1)
    return source.rstrip() + "\n" + FAILURE_METHOD


def patch_ready_asset(source: str) -> str:
    """Require both pinned files in the client cache OR Revival CDN overlay.

    A clean first-run must install their packs before Lapis is started. After
    the CDN hardlinks are created, normal client cache evictions do not force
    repeat downloads or require the internet on later launches.
    """
    signature = ".method public static ready(Landroid/content/Context;)Z"
    blocks = list(re.finditer(
        r"(?ms)^" + re.escape(signature) + r"\n.*?^\.end method$", source,
    ))
    if len(blocks) != 1:
        raise ValueError("Expected one pinned DataUpdates.ready method")
    block = blocks[0].group()
    old = f'const-string v2, "{STALE_READY_FILE}"'
    check = "invoke-virtual {v0}, Ljava/io/File;->isFile()Z"
    if (block.count(old) != 1 or block.count(check) != 3
            or ":mene_pin_0_ready" in block):
        raise ValueError("Unsupported or already updated readiness sentinel")
    old_begin = block.rfind("    new-instance v0, Ljava/io/File;", 0, block.index(old))
    old_end = block.index("    const/4 v0, 0x1", block.index(old))
    replaced = block[old_begin:old_end]
    if (old_begin < 0 or replaced.count(old) != 1
            or replaced.count(check) != 1
            or "if-eqz v0, :cond_0" not in replaced):
        raise ValueError("Pinned ready native file check changed")
    guards = []
    for i, (_pack, name) in enumerate(PINNED_MST_PACKS):
        checks = []
        for location in (f"mst/{name}", f"exvius/server-root/overlay/mst/{name}"):
            checks.append(f"""    new-instance v0, Ljava/io/File;
    invoke-virtual {{p0}}, Landroid/content/Context;->getFilesDir()Ljava/io/File;
    move-result-object v1
    const-string v2, "{location}"
    invoke-direct {{v0, v1, v2}}, Ljava/io/File;-><init>(Ljava/io/File;Ljava/lang/String;)V
    invoke-virtual {{v0}}, Ljava/io/File;->isFile()Z
    move-result v0""")
        guards.append(checks[0] + f"""
    if-nez v0, :mene_pin_{i}_ready
""" + checks[1] + f"""
    if-eqz v0, :cond_0
    :mene_pin_{i}_ready
""")
    revised = block[:old_begin] + "\n".join(guards) + block[old_end:]
    return source[:blocks[0].start()] + revised + source[blocks[0].end():]


def patch_missing_pack_receipt(source: str) -> str:
    """Invalidate only missing-pinned-pack receipts in memory, never saves.

    If the corresponding file already exists in the preserved CDN overlay,
    a client-side cache eviction does NOT trigger another download.
    DataUpdates remains responsible for pack SHA-256 and extraction.
    """
    signature = ".method private static installed(Landroid/content/Context;)Lorg/json/JSONObject;"
    blocks = list(re.finditer(
        r"(?ms)^" + re.escape(signature) + r"\n.*?^\.end method$", source,
    ))
    if len(blocks) != 1:
        raise ValueError("Expected exactly one pinned DataUpdates.installed method")
    block = blocks[0].group()
    anchor = "    :goto_0\n    return-object v1"
    if (block.count("    .locals 3") != 1 or block.count(anchor) != 1
            or ":mene_repair_0_done" in block):
        raise ValueError("Unsupported or already patched installed receipt")
    sections = []
    for i, (pack, name) in enumerate(PINNED_MST_PACKS):
        sections.append(f"""    # A pack receipt is trusted if its original OR its immutable CDN copy exists.
    new-instance v0, Ljava/io/File;
    invoke-virtual {{p0}}, Landroid/content/Context;->getFilesDir()Ljava/io/File;
    move-result-object v2
    const-string v3, "mst/{name}"
    invoke-direct {{v0, v2, v3}}, Ljava/io/File;-><init>(Ljava/io/File;Ljava/lang/String;)V
    invoke-virtual {{v0}}, Ljava/io/File;->isFile()Z
    move-result v0
    if-nez v0, :mene_repair_{i}_done
    new-instance v0, Ljava/io/File;
    invoke-virtual {{p0}}, Landroid/content/Context;->getFilesDir()Ljava/io/File;
    move-result-object v2
    const-string v3, "exvius/server-root/overlay/mst/{name}"
    invoke-direct {{v0, v2, v3}}, Ljava/io/File;-><init>(Ljava/io/File;Ljava/lang/String;)V
    invoke-virtual {{v0}}, Ljava/io/File;->isFile()Z
    move-result v0
    if-nez v0, :mene_repair_{i}_done
    const-string v0, "packs"
    invoke-virtual {{v1, v0}}, Lorg/json/JSONObject;->optJSONArray(Ljava/lang/String;)Lorg/json/JSONArray;
    move-result-object v2
    if-eqz v2, :mene_repair_{i}_done
    const/4 v3, 0x0
    :mene_repair_{i}_scan
    invoke-virtual {{v2}}, Lorg/json/JSONArray;->length()I
    move-result v4
    if-ge v3, v4, :mene_repair_{i}_done
    invoke-virtual {{v2, v3}}, Lorg/json/JSONArray;->optJSONObject(I)Lorg/json/JSONObject;
    move-result-object v4
    if-eqz v4, :mene_repair_{i}_skip
    const-string v5, "id"
    invoke-virtual {{v4, v5}}, Lorg/json/JSONObject;->optString(Ljava/lang/String;)Ljava/lang/String;
    move-result-object v4
    const-string v5, "{pack}"
    invoke-virtual {{v5, v4}}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v4
    if-eqz v4, :mene_repair_{i}_skip
    invoke-virtual {{v2, v3}}, Lorg/json/JSONArray;->remove(I)Ljava/lang/Object;
    goto :mene_repair_{i}_done
    :mene_repair_{i}_skip
    add-int/lit8 v3, v3, 0x1
    goto :mene_repair_{i}_scan
    :mene_repair_{i}_done""")
    guard = "    :goto_0\n" + "\n".join(sections) + "\n    return-object v1"
    revised = block.replace("    .locals 3", "    .locals 6", 1)
    revised = revised.replace(anchor, guard, 1)
    return source[:blocks[0].start()] + revised + source[blocks[0].end():]


def patch_smali(decoded) -> None:
    """Only mutate the scratch upstream decode after all guards have passed."""
    activity = decoded / ACTIVITY_PATH
    updates = decoded / UPDATES_PATH
    gate = decoded / READINESS_PATH
    if gate.exists() or not activity.is_file() or not updates.is_file():
        raise ValueError("Unexpected upstream gate state")
    modified = patch_activity(activity.read_text(encoding="utf-8"))
    revised_updates = patch_missing_pack_receipt(
        patch_ready_asset(updates.read_text(encoding="utf-8"))
    )
    # All guards passed before any writes; preserve original source outside scratch.
    gate.parent.mkdir(parents=True, exist_ok=True)
    activity.write_text(modified, encoding="utf-8")
    updates.write_text(revised_updates, encoding="utf-8")
    gate.write_text(READINESS_CLASS, encoding="utf-8")
