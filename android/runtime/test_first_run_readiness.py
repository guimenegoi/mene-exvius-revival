"""No-binary tests for the pinned upstream first-run readiness patch."""
from __future__ import annotations

import importlib.util
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from types import SimpleNamespace

from first_run_readiness import (
    ACTIVITY_PATH, READINESS_PATH, READINESS_CLASS, UPDATES_PATH,
    STALE_READY_FILE, PINNED_READY_FILE, GATE_METHOD,
    patch_activity, patch_ready_asset, patch_smali,
)

SOURCE = """.class public final Lcom/exvius/local/DataDownloadActivity;
.super Landroid/app/Activity;
.field private progress:Landroid/widget/ProgressBar;
.field private status:Landroid/widget/TextView;
.method private openGame(Z)V
    .locals 3
    :try_start_0
    invoke-static {v0}, Lcom/exvius/local/GameAssets;->attach(Landroid/content/Context;)V
    :try_end_0
    if-eqz p1, :cond_0
    invoke-static {p0}, Lcom/exvius/local/DataUpdates;->checkInBackground(Landroid/content/Context;)V
    :cond_0
    new-instance v0, Landroid/content/Intent;
    invoke-direct {v0}, Landroid/content/Intent;-><init>()V
    const-string v2, "com.square_enix.android_googleplay.FFBEWW.Lapis"
    invoke-virtual {v0, v1, v2}, Landroid/content/Intent;->setClassName(Ljava/lang/String;Ljava/lang/String;)Landroid/content/Intent;
    .line 81
    invoke-virtual {p0, v0}, Lcom/exvius/local/DataDownloadActivity;->startActivity(Landroid/content/Intent;)V

    .line 82
    invoke-virtual {p0}, Lcom/exvius/local/DataDownloadActivity;->finish()V
    .line 83
    return-void
.end method
.method private showDownloadPage()V
    .locals 1
    return-void
.end method
"""


UPDATES = """.class public Lcom/exvius/local/DataUpdates;
.super Ljava/lang/Object;
.method public static ready(Landroid/content/Context;)Z
    .locals 3
    invoke-virtual {v0}, Ljava/io/File;->isFile()Z
    move-result v0
    invoke-virtual {v0}, Ljava/io/File;->isFile()Z
    move-result v0
    const-string v2, "mst/Ver9001_YW9MUm2H.dat"
    invoke-virtual {v0}, Ljava/io/File;->isFile()Z
    move-result v0
    return v0
.end method
"""


class FirstRunReadinessTests(unittest.TestCase):
    def test_gate_replaces_only_immediate_launch(self):
        patched = patch_activity(SOURCE)
        self.assertEqual(patched.count(GATE_METHOD), 1)
        self.assertNotIn("->startActivity(Landroid/content/Intent;)V", patched)
        self.assertIn(".field private readinessStarted:Z", patched)
        self.assertIn("->showDownloadPage()V", patched)
        self.assertIn("Starting the offline game server", patched)
        self.assertIn(".method public showReadinessFailure(Ljava/lang/String;)V", patched)
        self.assertIn("->retry:Landroid/widget/Button;", patched)
        self.assertIn("const/16 v1, 0x8", patched)
        self.assertIn("GameAssets;->attach", patched)
        self.assertIn("checkInBackground", patched)
        self.assertIn("->setClassName", patched)

    def test_reject_unknown_version_and_reapplication(self):
        with self.assertRaisesRegex(ValueError, "already patched"):
            patch_activity(patch_activity(SOURCE))
        with self.assertRaisesRegex(ValueError, "Unknown upstream"):
            patch_activity(SOURCE.replace(
                "Lcom/exvius/local/GameAssets;->attach(",
                "Lcom/exvius/local/GameAssets;->something(",
            ))
        with self.assertRaisesRegex(ValueError, "single guarded"):
            patch_activity(SOURCE.replace(".line 82", ".line 99"))

    def test_add_class_once_without_touching_other_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            activity = root / ACTIVITY_PATH
            activity.parent.mkdir(parents=True)
            activity.write_text(SOURCE)
            updates = root / UPDATES_PATH
            updates.write_text(UPDATES)
            other = root / "untouched.txt"
            other.write_text("keep")
            patch_smali(root)
            self.assertEqual((root / READINESS_PATH).read_text(), READINESS_CLASS)
            self.assertIn(GATE_METHOD, activity.read_text())
            self.assertIn(f'const-string v2, "{PINNED_READY_FILE}"', updates.read_text())
            self.assertEqual(updates.read_text().count("->isDirectory()Z"), 1)
            self.assertNotIn(STALE_READY_FILE, updates.read_text())
            self.assertEqual(other.read_text(), "keep")
            with self.assertRaisesRegex(ValueError, "gate state"):
                patch_smali(root)

    def test_pinned_ready_sentry_is_exact_and_fails_closed(self):
        patched = patch_ready_asset(UPDATES)
        self.assertEqual(patched.count(f'const-string v2, "{PINNED_READY_FILE}"'), 1)
        self.assertEqual(patched.count("->isDirectory()Z"), 1)
        self.assertEqual(patched.count("->isFile()Z"), 2)
        self.assertNotIn(STALE_READY_FILE, patched)
        with self.assertRaisesRegex(ValueError, "already updated"):
            patch_ready_asset(patched)
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            patch_ready_asset(UPDATES.replace(STALE_READY_FILE, "mst/not-shipped.dat"))
        with self.assertRaisesRegex(ValueError, "native directory check"):
            patch_ready_asset(UPDATES.replace("->isFile()Z", "->exists()Z"))
        with self.assertRaisesRegex(ValueError, "Expected one"):
            patch_ready_asset("no upstream ready method")

    def test_hello_handler_exposes_the_expected_readiness_reply(self):
        """Contract check using serve.py's real handler, not the game engine."""
        path = Path(__file__).resolve().parents[2] / "ios-server/serve.py"
        spec = importlib.util.spec_from_file_location("ffbe_readiness_serve", path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        server_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server_module)

        class Base(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_error(404)

            def log_message(self, *args):
                pass

        handler = server_module.make_handler(SimpleNamespace(Handler=Base), b"", b"")
        server = server_module.Server(("127.0.0.1", 0), handler)
        server.tls = None
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        try:
            thread.start()
            url = f"http://127.0.0.1:{server.server_address[1]}/__exvius/hello"
            with urllib.request.urlopen(url, timeout=3) as response:
                self.assertEqual(response.status, 200)
                body = response.read(4097)
                self.assertLessEqual(len(body), 4096)
                self.assertIn(b"Reachable. You can open the game.", body)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)
        self.assertFalse(thread.is_alive())

    def test_runtime_starts_async_worker_and_checks_real_local_http(self):
        self.assertIn("LocalPythonProbe;->probe()V", READINESS_CLASS)
        self.assertIn("LocalPythonProbe;->startAsync(", READINESS_CLASS)
        self.assertLess(READINESS_CLASS.index("LocalPythonProbe;->probe()V"),
                        READINESS_CLASS.index("LocalPythonProbe;->startAsync("))
        self.assertIn("http://127.0.0.1:18080/__exvius/hello", READINESS_CLASS)
        self.assertIn("Reachable. You can open the game.", READINESS_CLASS)
        self.assertIn("FFBE-Readiness", READINESS_CLASS)
        self.assertIn("->runOnUiThread(Ljava/lang/Runnable;)V", READINESS_CLASS)
        self.assertIn("->isFinishing()Z", READINESS_CLASS)
        self.assertIn("->isDestroyed()Z", READINESS_CLASS)
        self.assertIn("->showReadinessFailure(Ljava/lang/String;)V", READINESS_CLASS)
        self.assertIn("const/16 v2, 0xf0", READINESS_CLASS)  # finite poll count
        self.assertNotIn("18081", READINESS_CLASS)
        self.assertNotIn("0.0.0.0", READINESS_CLASS)


if __name__ == "__main__":
    unittest.main()
