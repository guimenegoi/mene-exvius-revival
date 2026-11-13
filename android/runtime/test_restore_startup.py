"""Synthetic Android bootstrap recovery tests. No actual game or save is used."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import restore_startup

# The Android archive renames save_restore -> ffbe_save_restore. Test that
# import alias without actually installing it in any real APK or game path.
BACKUP = Path(__file__).resolve().parent.parent / "backup"
if str(BACKUP) not in sys.path:
    sys.path.insert(0, str(BACKUP))
import lxc_backup
import save_restore
import restore_request


class RestoreBootGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.files = Path(self.tmp.name)
        self.root = self.files / "exvius/server-root"
        self.state = self.root / "state"
        self.recovery = self.root / "restore-private"

    def _setup_state(self):
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / "campaign.json").write_text('{"rank": 20}')
        (self.state / "replay.json").write_text('{"week": 17}')

    def _make_interrupted_restore(self):
        self._setup_state()
        alternate = self.files / "synthetic-archive"
        alternate.mkdir()
        (alternate / "campaign.json").write_text('{"rank": 1}')
        (alternate / "replay.json").write_text('{"week": 2}')
        data = lxc_backup.snapshot(alternate)
        digest = hashlib.sha256(data).hexdigest()
        before = lxc_backup.snapshot(self.state)
        real_replace = os.replace

        def fail_after_first_write(src, dest):
            if Path(dest) == self.state / "replay.json" and "staged" in str(src):
                raise KeyboardInterrupt("synthetic sudden process death")
            return real_replace(src, dest)

        with patch.object(save_restore.os, "replace", side_effect=fail_after_first_write):
            with self.assertRaises(KeyboardInterrupt):
                save_restore.restore_offline(
                    data, self.state, self.recovery,
                    expected_sha256=digest,
                    confirmation="RESTAURAR " + digest[:12],
                    game_stopped=lambda: True)
        self.assertTrue((self.recovery / "pending-restore.json").exists())
        return before

    def test_no_journal_no_save_directory_no_side_effect(self):
        self.assertEqual(
            restore_startup.recover_before_engine(self.files),
            "no_restore_journal")
        self.assertFalse(self.root.exists())

    def test_recovery_dir_present_but_no_journal_no_save_read(self):
        self.recovery.mkdir(parents=True)
        with patch.dict(sys.modules, {"ffbe_save_restore": None}):
            self.assertEqual(
                restore_startup.recover_before_engine(self.files),
                "no_restore_journal")
        self.assertFalse(self.state.exists())

    def test_reject_symlink_even_without_journal(self):
        target = self.files / "untrusted"
        target.mkdir()
        self.root.mkdir(parents=True)
        self.recovery.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            restore_startup.recover_before_engine(self.files)

    def test_reject_file_as_recovery_dir(self):
        self.root.mkdir(parents=True)
        self.recovery.write_text("not a directory")
        with self.assertRaisesRegex(RuntimeError, "not a directory"):
            restore_startup.recover_before_engine(self.files)

    def test_pending_journal_requires_engine_stopped(self):
        self._make_interrupted_restore()
        with patch.object(restore_startup, "_engine_stopped", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "may be running"):
                restore_startup.recover_before_engine(self.files)
        self.assertTrue((self.recovery / "pending-restore.json").exists())

    def test_pending_recovery_runs_before_engine_start(self):
        before = self._make_interrupted_restore()
        with patch.object(restore_startup, "_engine_stopped", return_value=True), \
                patch.dict(sys.modules, {"ffbe_save_restore": save_restore}):
            outcome = restore_startup.recover_before_engine(self.files)
        self.assertEqual(outcome, "interrupted_restore_rolled_back")
        self.assertEqual(lxc_backup.snapshot(self.state), before)
        self.assertFalse((self.recovery / "pending-restore.json").exists())

    def test_queued_request_applies_before_engine_starts(self):
        self._setup_state()
        source = self.files / "picked"
        source.mkdir()
        (source / "campaign.json").write_text('{"rank":4}')
        (source / "replay.json").write_text('{"week":1}')
        data = lxc_backup.snapshot(source)
        digest = hashlib.sha256(data).hexdigest()
        restore_request.stage_request(
            data, self.state, self.recovery,
            confirmation="RESTAURAR " + digest[:12])
        with (patch.object(restore_startup, "_engine_stopped", return_value=True),
              patch.dict(sys.modules, {"ffbe_restore_request": restore_request})):
            result = restore_startup.recover_before_engine(self.files)
        self.assertEqual(result, "restore_applied_" + digest[:12])
        self.assertEqual(json.loads((self.state / "campaign.json").read_text())["rank"], 4)
        self.assertFalse((self.recovery / restore_request.QUEUE).exists())

    def test_queued_request_never_applies_with_active_engine(self):
        self._setup_state()
        source = self.files / "picked"
        source.mkdir()
        (source / "campaign.json").write_text('{"rank":4}')
        data = lxc_backup.snapshot(source)
        digest = hashlib.sha256(data).hexdigest()
        restore_request.stage_request(
            data, self.state, self.recovery,
            confirmation="RESTAURAR " + digest[:12])
        with patch.object(restore_startup, "_engine_stopped", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "may be running"):
                restore_startup.recover_before_engine(self.files)
        self.assertEqual(json.loads((self.state / "campaign.json").read_text())["rank"],20)
        self.assertTrue((self.recovery / restore_request.QUEUE).exists())

    def test_rollback_never_consumes_different_queued_request(self):
        before = self._make_interrupted_restore()
        source = self.files / "picked"
        source.mkdir()
        (source / "campaign.json").write_text('{"rank":4}')
        data = lxc_backup.snapshot(source)
        digest = hashlib.sha256(data).hexdigest()
        # Simulate a request arriving after the interrupted transaction.
        (self.recovery / ("request-" + digest + ".zip")).write_bytes(data)
        doc = {"schema":1, "archive":"request-" + digest + ".zip",
               "sha256":digest, "confirmation":"RESTAURAR " + digest[:12]}
        (self.recovery / restore_request.QUEUE).write_text(json.dumps(doc))
        os.chmod(self.recovery / restore_request.QUEUE, 0o600)
        with (patch.object(restore_startup, "_engine_stopped", return_value=True),
              patch.dict(sys.modules, {"ffbe_save_restore": save_restore,
                                      "ffbe_restore_request": restore_request})):
            result = restore_startup.recover_before_engine(self.files)
        self.assertEqual(result, "interrupted_restore_rolled_back")
        self.assertEqual(lxc_backup.snapshot(self.state), before)
        self.assertTrue((self.recovery / restore_request.QUEUE).exists())

    def test_tampered_journal_fails_closed(self):
        self._make_interrupted_restore()
        pending = self.recovery / "pending-restore.json"
        pending.write_text('{"unexpected":"tampering"}')
        os.chmod(pending, 0o600)
        with patch.object(restore_startup, "_engine_stopped", return_value=True), \
                patch.dict(sys.modules, {"ffbe_save_restore": save_restore}):
            with self.assertRaisesRegex(ValueError, "journal fields"):
                restore_startup.recover_before_engine(self.files)
        self.assertTrue(pending.exists())

    def test_engine_stopped_requires_no_engine_import(self):
        with patch.dict(sys.modules, {"serve": types.ModuleType("serve")}):
            self.assertFalse(restore_startup._engine_stopped())
        with patch.dict(sys.modules, {"capture_server": types.ModuleType("capture_server")}):
            self.assertFalse(restore_startup._engine_stopped())

    def test_engine_stopped_refuses_listening_port(self):
        with patch.object(restore_startup.socket, "create_connection") as connect:
            connect.return_value.__enter__.return_value = object()
            self.assertFalse(restore_startup._engine_stopped())

    def test_engine_stopped_accepts_only_refused_connection(self):
        with patch.object(restore_startup.socket, "create_connection",
                          side_effect=ConnectionRefusedError(111, "refused")):
            with patch.dict(sys.modules, {}, clear=False):
                sys.modules.pop("serve", None)
                sys.modules.pop("capture_server", None)
                self.assertTrue(restore_startup._engine_stopped())
        with patch.object(restore_startup.socket, "create_connection",
                          side_effect=OSError(101, "unreachable")):
            self.assertFalse(restore_startup._engine_stopped())


if __name__ == "__main__":
    unittest.main()
