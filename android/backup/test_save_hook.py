"""Tests for opt-in asynchronous backup scheduling without network or real saves."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source/server"))
import save_backup


class SaveHookTests(unittest.TestCase):
    def setUp(self):
        save_backup._LAST_ATTEMPT = None
        save_backup._RUNNING = False

    def test_no_config_never_starts_backup(self):
        with patch.dict(os.environ, {"FFBE_ANDROID_EMBEDDED": "1"}, clear=True), \
             patch.object(save_backup.threading.Thread, "start") as start:
            self.assertFalse(save_backup.after_save("/tmp/state/campaign.json"))
            start.assert_not_called()

    def test_no_android_or_other_slot_never_starts(self):
        with patch.dict(os.environ, {"FFBE_SAVE_BACKUP_CONFIG": "/missing"}, clear=True):
            self.assertFalse(save_backup.after_save("/tmp/state/campaign.json"))
        with patch.dict(os.environ, {"FFBE_ANDROID_EMBEDDED": "1",
                                     "FFBE_SAVE_BACKUP_CONFIG": "/missing"}, clear=True):
            self.assertFalse(save_backup.after_save("/tmp/state/test.json"))

    def test_private_configuration_and_no_secret_in_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, token, ca = [root / x for x in ("config.json", "token", "ca.pem")]
            token.write_text("a" * 40)
            token.chmod(0o600)
            ca.write_text("certificate")
            cfg.write_text(json.dumps({"enabled": True, "url": "https://example.test",
                                       "device": "phone", "token_file": str(token), "ca_file": str(ca)}))
            cfg.chmod(0o600)
            with patch.dict(os.environ, {"FFBE_ANDROID_EMBEDDED": "1",
                                         "FFBE_SAVE_BACKUP_CONFIG": str(cfg)}):
                self.assertEqual(save_backup._configuration()[:3],
                                 ("https://example.test", "phone", "a" * 40))
                cfg.chmod(0o644)
                with self.assertRaisesRegex(ValueError, "private"):
                    save_backup._configuration()

    def test_successful_save_schedules_one_worker_and_throttles(self):
        with patch.dict(os.environ, {"FFBE_ANDROID_EMBEDDED": "1",
                                     "FFBE_SAVE_BACKUP_CONFIG": "/missing"}, clear=True), \
             patch.object(save_backup.threading.Thread, "start") as start:
            self.assertTrue(save_backup.after_save("/tmp/state/campaign.json"))
            self.assertFalse(save_backup.after_save("/tmp/state/campaign.json"))
            start.assert_called_once()

    def test_worker_failure_does_not_raise_or_leak_credentials(self):
        with patch.object(save_backup, "_configuration", side_effect=OSError("secret")), \
             patch("builtins.print") as printed:
            save_backup._RUNNING = True
            save_backup._send(Path("/tmp/state"))
            self.assertFalse(save_backup._RUNNING)
            message = str(printed.call_args.args[0])
            self.assertIn("OSError", message)
            self.assertNotIn("secret", message)


if __name__ == "__main__":
    unittest.main()
