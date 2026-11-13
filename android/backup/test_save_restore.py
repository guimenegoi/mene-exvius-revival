"""Offline-only synthetic tests. Never read actual FFBE saves or connect to LXC API."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import lxc_backup as backup
import save_restore as restore


class SaveRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.recovery = self.root / "restore-private"
        self._write("campaign.json", {"chapter": 12, "rank": 34})
        self._write("replay.json", {"week": 11})
        (self.state / "backups").mkdir()
        (self.state / "backups" / "retained.json").write_text('{"untouched": true}')
        self.new_state = self.root / "source"
        self.new_state.mkdir()
        (self.new_state / "campaign.json").write_text('{"chapter":2,"rank":3}')
        (self.new_state / "replay.json").write_text('{"week":1}')
        self.data = backup.snapshot(self.new_state)
        self.digest = hashlib.sha256(self.data).hexdigest()
        self.confirm = "RESTAURAR " + self.digest[:12]
        self.stopped = lambda: True

    def _write(self, name, obj):
        (self.state / name).write_text(json.dumps(obj))

    def _restore(self, **kwargs):
        params = {
            "expected_sha256": self.digest,
            "confirmation": self.confirm,
            "game_stopped": self.stopped,
        }
        params.update(kwargs)
        return restore.restore_offline(
            self.data, self.state, self.recovery, **params)

    def test_plan_digest_and_confirmation(self):
        plan = restore.inspect_archive(self.data, self.digest)
        self.assertEqual(plan["files"], ["campaign.json", "replay.json"])
        self.assertEqual(plan["confirmation"], self.confirm)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            restore.inspect_archive(self.data, "0" * 64)

    def test_restore_creates_private_prebackup_with_exact_original(self):
        before = backup.snapshot(self.state)
        receipt = self._restore()
        self.assertEqual(receipt["sha256"], self.digest)
        self.assertEqual(restore._fingerprints(self.state),
                         restore._fingerprints(self.new_state))
        pre = self.recovery / receipt["pre_restore_file"]
        self.assertEqual(pre.read_bytes(), before)
        self.assertEqual(pre.stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.recovery / restore.JOURNAL).exists())
        self.assertTrue((self.state / "backups" / "retained.json").is_file())

    def test_restoring_removes_extra_save_but_not_unrelated_folders(self):
        self._write("extra.json", {"future": True})
        self._restore()
        self.assertFalse((self.state / "extra.json").exists())
        self.assertTrue((self.state / "backups" / "retained.json").is_file())

    def test_explicit_confirmation_required_without_changes(self):
        original = backup.snapshot(self.state)
        with self.assertRaises(PermissionError):
            self._restore(confirmation="RESTAURAR WRONG")
        self.assertEqual(backup.snapshot(self.state), original)
        self.assertFalse(self.recovery.exists())

    def test_cannot_restore_while_game_running(self):
        original = backup.snapshot(self.state)
        with self.assertRaisesRegex(RuntimeError, "stopped"):
            self._restore(game_stopped=lambda: False)
        self.assertEqual(backup.snapshot(self.state), original)
        self.assertFalse(self.recovery.exists())

    def test_invalid_archive_refused_without_write(self):
        corrupt = self.data[:-25] + b"garbage"
        with self.assertRaises(ValueError):
            restore.restore_offline(corrupt, self.state, self.recovery,
                expected_sha256=self.digest, confirmation=self.confirm,
                game_stopped=self.stopped)
        self.assertFalse(self.recovery.exists())

    def test_invalid_recovery_directory_symlink_refused(self):
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        self.recovery.symlink_to(elsewhere, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Unsafe recovery"):
            self._restore()
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_hardlinked_current_save_refused(self):
        source = self.root / "hardlinked.json"
        source.write_text('{"ok":true}')
        (self.state / "replay.json").unlink()
        os.link(source, self.state / "replay.json")
        with self.assertRaisesRegex(ValueError, "hardlink"):
            self._restore()

    def test_recover_immediately_when_replace_fails(self):
        original = backup.snapshot(self.state)
        real = os.replace
        triggered = False

        def fail_once(src, dest):
            nonlocal triggered
            if (not triggered and Path(dest) == self.state / "replay.json"
                    and "staged" in str(src)):
                triggered = True
                raise OSError("synthetic interrupted write")
            return real(src, dest)

        with patch.object(restore.os, "replace", side_effect=fail_once):
            with self.assertRaisesRegex(RuntimeError, "previous save recovered"):
                self._restore()
        self.assertTrue(triggered)
        self.assertEqual(backup.snapshot(self.state), original)
        self.assertFalse((self.recovery / restore.JOURNAL).exists())

    def test_recover_after_simulated_process_crash(self):
        original = backup.snapshot(self.state)
        real = os.replace

        def simulate_sigkill(src, dest):
            if Path(dest) == self.state / "replay.json" and "staged" in str(src):
                raise KeyboardInterrupt("simulated abrupt process exit")
            return real(src, dest)

        with patch.object(restore.os, "replace", side_effect=simulate_sigkill):
            with self.assertRaises(KeyboardInterrupt):
                self._restore()
        self.assertTrue((self.recovery / restore.JOURNAL).exists())
        with self.assertRaisesRegex(RuntimeError, "stopped"):
            restore.recover_pending(self.state, self.recovery,
                                    game_stopped=lambda: False)
        self.assertTrue((self.recovery / restore.JOURNAL).exists())
        self.assertTrue(restore.recover_pending(self.state, self.recovery,
                                                game_stopped=self.stopped))
        self.assertEqual(backup.snapshot(self.state), original)
        self.assertFalse((self.recovery / restore.JOURNAL).exists())
        self.assertFalse(restore.recover_pending(self.state, self.recovery,
                                                 game_stopped=self.stopped))

    def test_failed_prebackup_digest_cannot_restore(self):
        real = os.replace

        def interrupt(src, dest):
            if Path(dest) == self.state / "replay.json" and "staged" in str(src):
                raise KeyboardInterrupt("synthetic crash")
            return real(src, dest)
        with patch.object(restore.os, "replace", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self._restore()
        journal = restore._load_journal(self.recovery / restore.JOURNAL)
        (self.recovery / journal["pre_file"]).write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            restore.recover_pending(self.state, self.recovery,
                                    game_stopped=self.stopped)
        self.assertTrue((self.recovery / restore.JOURNAL).exists())

    def test_restore_rejects_preexisting_pending_journal(self):
        self.recovery.mkdir()
        (self.recovery / restore.JOURNAL).write_text("{}", encoding="ascii")
        with self.assertRaisesRegex(RuntimeError, "Interrupted restore"):
            self._restore()
        self.assertEqual(json.loads((self.state / "campaign.json").read_text())["rank"],34)

    def test_zip_path_traversal_refused(self):
        with tempfile.TemporaryFile() as buf:
            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as z:
                z.writestr("manifest.json", '{"schema":1,"files":{"campaign.json":"' + "0"*64 + '"}}')
                z.writestr("state/../campaign.json", '{"rank":1}')
            buf.seek(0)
            attack = buf.read()
        with self.assertRaises(ValueError):
            restore.inspect_archive(attack, hashlib.sha256(attack).hexdigest())


if __name__ == "__main__":
    unittest.main()
