"""Synthetic one-shot restore request tests. Never touches the real game."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import lxc_backup as backup
import restore_request as request
import save_restore as restore


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.recovery = self.root / "restore-private"
        (self.state / "campaign.json").write_text('{"rank":19}')
        (self.state / "replay.json").write_text('{"week":10}')
        source = self.root / "archive"
        source.mkdir()
        (source / "campaign.json").write_text('{"rank":3}')
        (source / "replay.json").write_text('{"week":1}')
        self.data = backup.snapshot(source)
        self.digest = hashlib.sha256(self.data).hexdigest()
        self.confirm = "RESTAURAR " + self.digest[:12]
        self.previous = backup.snapshot(self.state)

    def _stage(self, **kwargs):
        return request.stage_request(self.data, self.state, self.recovery,
                                     confirmation=kwargs.get("confirmation", self.confirm))

    def test_staging_never_mutates_active_save(self):
        receipt = self._stage()
        self.assertEqual(receipt["sha256"], self.digest)
        self.assertEqual(backup.snapshot(self.state), self.previous)
        meta = self.recovery / request.QUEUE
        staged = self.recovery / ("request-" + self.digest + ".zip")
        self.assertTrue(meta.is_file() and staged.is_file())
        self.assertEqual(meta.stat().st_mode & 0o777, 0o600)
        self.assertEqual(staged.stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.recovery / request.PROCESSING).exists())

    def test_cold_start_applies_once_with_prebackup(self):
        self._stage()
        result = request.consume_request(self.state, self.recovery, game_stopped=lambda: True)
        self.assertEqual(result, "restore_applied_" + self.digest[:12])
        self.assertEqual(json.loads((self.state / "campaign.json").read_text())["rank"], 3)
        self.assertFalse((self.recovery / request.QUEUE).exists())
        self.assertFalse((self.recovery / request.PROCESSING).exists())
        self.assertFalse((self.recovery / ("request-" + self.digest + ".zip")).exists())
        self.assertEqual(len(list(self.recovery.glob("pre-*.zip"))), 1)
        self.assertEqual(request.consume_request(self.state, self.recovery,
            game_stopped=lambda: True), "no_restore_request")

    def test_wrong_confirmation_refuses_even_to_stage(self):
        with self.assertRaises(PermissionError):
            self._stage(confirmation="RESTAURAR WRONG")
        self.assertEqual(self.previous, backup.snapshot(self.state))
        self.assertFalse(self.recovery.exists())

    def test_second_request_is_not_allowed(self):
        self._stage()
        with self.assertRaisesRegex(RuntimeError, "already pending"):
            self._stage()
        self.assertTrue((self.recovery / request.QUEUE).exists())

    def test_engine_running_refuses_consumption_without_mutation(self):
        self._stage()
        with self.assertRaisesRegex(RuntimeError, "stopped"):
            request.consume_request(self.state, self.recovery, game_stopped=lambda: False)
        self.assertEqual(self.previous, backup.snapshot(self.state))
        self.assertTrue((self.recovery / request.QUEUE).exists())

    def test_tampered_archive_prevents_restore(self):
        self._stage()
        path = self.recovery / ("request-" + self.digest + ".zip")
        path.write_bytes(path.read_bytes() + b"x")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            request.consume_request(self.state, self.recovery, game_stopped=lambda: True)
        self.assertTrue((self.recovery / request.QUEUE).exists())
        self.assertEqual(self.previous, backup.snapshot(self.state))

    def test_unconfirmed_metadata_prevents_restore(self):
        self._stage()
        path = self.recovery / request.QUEUE
        doc = json.loads(path.read_text("ascii"))
        doc["confirmation"] = "NOT CONFIRMED"
        path.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError, "Unconfirmed"):
            request.consume_request(self.state, self.recovery, game_stopped=lambda: True)
        self.assertEqual(self.previous, backup.snapshot(self.state))

    def test_malicious_request_filename_refused(self):
        self._stage()
        path = self.recovery / request.QUEUE
        doc = json.loads(path.read_text("ascii"))
        doc["archive"] = "../someone-else.zip"
        path.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError, "Unconfirmed"):
            request.consume_request(self.state, self.recovery, game_stopped=lambda: True)
        self.assertEqual(self.previous, backup.snapshot(self.state))

    def test_request_symlink_refused_without_unlink(self):
        self._stage()
        outside = self.root / "outside.json"
        outside.write_text("something")
        path = self.recovery / request.QUEUE
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "Invalid restore request"):
            request.consume_request(self.state, self.recovery, game_stopped=lambda: True)
        self.assertEqual(outside.read_text(), "something")

    def test_interrupted_queued_restore_not_repeated(self):
        self._stage()
        real_replace = os.replace

        def interrupt(src, dest):
            if Path(dest) == self.state / "replay.json" and "staged" in str(src):
                raise KeyboardInterrupt("simulated process death")
            return real_replace(src, dest)

        with patch.object(restore.os, "replace", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                request.consume_request(self.state, self.recovery, game_stopped=lambda: True)
        self.assertFalse((self.recovery / request.QUEUE).exists())
        self.assertTrue((self.recovery / request.PROCESSING).exists())
        self.assertTrue((self.recovery / restore.JOURNAL).exists())
        self.assertTrue(restore.recover_pending(
            self.state, self.recovery, game_stopped=lambda: True))
        self.assertEqual(backup.snapshot(self.state), self.previous)
        self.assertEqual(request.consume_request(
            self.state, self.recovery, game_stopped=lambda: True),
            "interrupted_restore_request_discarded")
        self.assertEqual(request.consume_request(self.state, self.recovery,
            game_stopped=lambda: True), "no_restore_request")
        self.assertEqual(backup.snapshot(self.state), self.previous)

    def test_processing_marker_blocks_double_restore(self):
        self._stage()
        (self.recovery / request.QUEUE).rename(self.recovery / request.PROCESSING)
        self.assertEqual(request.consume_request(
            self.state, self.recovery, game_stopped=lambda: True),
            "interrupted_restore_request_discarded")
        self.assertEqual(backup.snapshot(self.state), self.previous)

    def test_active_journal_blocks_new_queue(self):
        self.recovery.mkdir()
        (self.recovery / restore.JOURNAL).write_text("{}")
        with self.assertRaisesRegex(RuntimeError, "already pending"):
            self._stage()
        self.assertEqual(backup.snapshot(self.state), self.previous)


if __name__ == "__main__":
    unittest.main()
