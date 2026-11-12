"""Contract checks for a worker-thread-only CPython lab bootstrap."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import patch_async_python as async_patch
import patch_python_execute as sync_patch
from patch_bootstrap_probe import LAPIS, SUPER_CREATE
from test_python_execute import fixture


class AsyncPythonTests(unittest.TestCase):
    def prepared(self, folder: Path) -> None:
        fixture(folder)
        sync_patch.prepare(folder)

    def test_activity_schedules_one_worker_after_super(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepared(root)
            changes = async_patch.prepare(root)
            self.assertEqual(len(changes), 3)
            lapis = (root / LAPIS).read_text()
            helper = (root / async_patch.PROBE_PATH).read_text()
            worker = (root / async_patch.WORKER_PATH).read_text()
            self.assertLess(lapis.index(SUPER_CREATE), lapis.index(async_patch.ASYNC_START))
            self.assertNotIn(async_patch.RUN_DEMO, lapis)
            self.assertEqual(lapis.count(async_patch.ASYNC_START), 1)
            self.assertIn(".method public static synchronized startAsync(", helper)
            self.assertIn(".field private static started:Z", helper)
            self.assertIn("->getApplicationContext()", helper)
            self.assertIn("->start()V", helper)
            self.assertIn("FFBE-Python", helper)
            self.assertIn("Ljava/lang/Runnable;", worker)
            self.assertIn("->runDemo(Landroid/content/Context;)V", worker)
            self.assertIn("async worker started", worker)
            self.assertNotIn("->execute(Landroid/content/Context;)", worker)

    def test_double_patch_rejected_without_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepared(root)
            async_patch.prepare(root)
            files = [root / name for name in
                     (LAPIS, async_patch.PROBE_PATH, async_patch.WORKER_PATH)]
            before = [file.read_bytes() for file in files]
            with self.assertRaisesRegex(ValueError, "without async worker"):
                async_patch.prepare(root)
            self.assertEqual(before, [file.read_bytes() for file in files])

    def test_unexpected_lifecycle_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepared(root)
            activity = root / LAPIS
            activity.write_text(activity.read_text().replace(
                async_patch.RUN_DEMO, "    nop",
            ))
            before = [activity.read_bytes(),
                      (root / async_patch.PROBE_PATH).read_bytes()]
            with self.assertRaisesRegex(ValueError, "synchronous execution"):
                async_patch.prepare(root)
            self.assertEqual(before, [activity.read_bytes(),
                                     (root / async_patch.PROBE_PATH).read_bytes()])
            self.assertFalse((root / async_patch.WORKER_PATH).exists())

    def test_unexpected_helper_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepared(root)
            probe = root / async_patch.PROBE_PATH
            probe.write_text(probe.read_text().replace(
                ".method public static runDemo(",
                ".method public static runWrongDemo(",
            ))
            activity = root / LAPIS
            before = activity.read_bytes()
            with self.assertRaisesRegex(ValueError, "helper missing"):
                async_patch.prepare(root)
            self.assertEqual(before, activity.read_bytes())
            self.assertFalse((root / async_patch.WORKER_PATH).exists())

    def test_only_single_super_and_hook_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepared(root)
            activity = root / LAPIS
            activity.write_text(activity.read_text().replace(
                async_patch.RUN_DEMO,
                async_patch.RUN_DEMO + "\n" + async_patch.RUN_DEMO,
            ))
            with self.assertRaisesRegex(ValueError, "synchronous execution"):
                async_patch.prepare(root)
            self.assertFalse((root / async_patch.WORKER_PATH).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
