"""Synthetic guardrails for 2016 historical migration.

No phone, Proxmox save, production setting or real FFBE archive is accessed.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import config_model
import lxc_backup as backup
import replay_anchor_migration as migration
import save_restore


def doc(**items):
    return {"schema": 1, "settings": items}


class HistoricalMigrationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.cfg = self.root / "private-config"
        self.cfg.mkdir(mode=0o700)
        self.rest = self.root / "restore-private"
        (self.state / "campaign.json").write_text('{"player":"test","rank":20}')
        (self.state / "replay.json").write_text(
            json.dumps({"anchor_week": 44, "start": "2016-12-16"}))
        self.original = backup.snapshot(self.state)
        self.staged = doc(EXVIUS_REPLAY_START="2016-11-11")
        config_model.write_private(self.cfg / "staged-config.json", self.staged)

    def preview(self):
        return migration.preview_migration(self.state, self.cfg)

    def test_plan_never_mutates_campaign_replay_or_settings(self):
        before = (self.state / "replay.json").read_bytes()
        pending = (self.cfg / "staged-config.json").read_bytes()
        p = self.preview()
        self.assertEqual(backup.snapshot(self.state), self.original)
        self.assertEqual((self.state / "replay.json").read_bytes(), before)
        self.assertEqual((self.cfg / "staged-config.json").read_bytes(), pending)
        self.assertFalse(self.rest.exists())
        self.assertEqual(p["confirmation"], "MIGRAR HISTORICO 2016-11-11 " +
                         p["candidate_archive_sha256"][:12])

    def test_snapshot_preserves_campaign_and_week(self):
        p = self.preview()
        self.assertEqual(p["anchor_week"], 44)
        with zipfile.ZipFile(io.BytesIO(p["candidate_archive"])) as z:
            replay = json.loads(z.read("state/replay.json"))
            self.assertEqual(replay, {"anchor_week": 44, "start": "2016-11-11"})
            self.assertEqual(z.read("state/campaign.json"),
                (self.state / "campaign.json").read_bytes())
        self.assertEqual(backup.validate(p["candidate_archive"]),
                         ["campaign.json", "replay.json"])

    def test_no_staged_setting_fail_closed(self):
        (self.cfg / "staged-config.json").unlink()
        with self.assertRaisesRegex(ValueError, "not been received"):
            self.preview()

    def test_wrong_staged_date_rejected(self):
        config_model.write_private(self.cfg / "staged-config.json",
                                  doc(EXVIUS_REPLAY_START="2016-10-01"))
        with self.assertRaisesRegex(ValueError, "2016-11-11"):
            self.preview()

    def test_mismatched_active_setting_rejected(self):
        config_model.write_private(self.cfg / "server-config.json",
                                  doc(EXVIUS_REPLAY_START="2016-09-09"))
        with self.assertRaisesRegex(ValueError, "existing anchor"):
            self.preview()

    def test_seasonal_toggle_change_rejected(self):
        config_model.write_private(self.cfg / "staged-config.json",
             doc(EXVIUS_REPLAY_START="2016-11-11", EXVIUS_EVENT_ARCHIVE=False))
        with self.assertRaisesRegex(ValueError, "other settings"):
            self.preview()

    def test_seasonal_value_change_rejected_even_if_present_in_both(self):
        config_model.write_private(self.cfg / "server-config.json",
             doc(EXVIUS_EVENT_ARCHIVE=True))
        config_model.write_private(self.cfg / "staged-config.json",
             doc(EXVIUS_REPLAY_START="2016-11-11", EXVIUS_EVENT_ARCHIVE=False))
        with self.assertRaisesRegex(ValueError, "seasonal"):
            self.preview()

    def test_pace_change_rejected(self):
        config_model.write_private(self.cfg / "staged-config.json",
             doc(EXVIUS_REPLAY_START="2016-11-11", EXVIUS_REPLAY_PACE="2"))
        with self.assertRaisesRegex(ValueError, "pace"):
            self.preview()

    def test_invalid_replay_week_rejected(self):
        (self.state / "replay.json").write_text(
            '{"anchor_week":true,"start":"2016-12-16"}')
        with self.assertRaisesRegex(ValueError, "week"):
            self.preview()

    def test_foreign_replay_start_rejected(self):
        (self.state / "replay.json").write_text(
            '{"anchor_week":44,"start":"2016-06-30"}')
        with self.assertRaisesRegex(ValueError, "verified"):
            self.preview()

    def test_invalid_campaign_fail_closed(self):
        (self.state / "campaign.json").write_text("not-json")
        with self.assertRaises((ValueError, json.JSONDecodeError)):
            self.preview()

    def test_staged_config_symlink_is_refused(self):
        outside = self.root / "outsider.json"
        config_model.write_private(outside, self.staged)
        (self.cfg / "staged-config.json").unlink()
        (self.cfg / "staged-config.json").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.preview()
        self.assertEqual(backup.snapshot(self.state), self.original)

    def test_atomic_restore_then_settings_apply_with_synthetic_state(self):
        p = self.preview()
        receipt = save_restore.restore_offline(
            p["candidate_archive"], self.state, self.rest,
            expected_sha256=p["candidate_archive_sha256"],
            confirmation="RESTAURAR " + p["candidate_archive_sha256"][:12],
            game_stopped=lambda: True,
        )
        self.assertTrue((self.rest / receipt["pre_restore_file"]).is_file())
        self.assertEqual(receipt["pre_restore_sha256"],
                         hashlib.sha256(self.original).hexdigest())
        env = {}
        status = config_model.apply_on_boot(
            self.cfg, self.state / "replay.json", env)
        self.assertTrue(status["applied"])
        self.assertFalse(status["staged"])
        self.assertEqual(env["EXVIUS_REPLAY_START"], "2016-11-11")
        self.assertEqual(json.loads((self.state / "replay.json").read_text()),
                         {"anchor_week": 44, "start": "2016-11-11"})
        self.assertEqual((self.state / "campaign.json").read_text(),
                         '{"player":"test","rank":20}')

    def test_simulated_failure_rolls_back_and_staged_setting_stays(self):
        p = self.preview()
        real = os.replace
        fired = False

        def fail_once(src, dst):
            nonlocal fired
            if (not fired and Path(dst) == self.state / "replay.json"
                    and "staged" in str(src)):
                fired = True
                raise OSError("simulated disk write failure")
            return real(src, dst)

        with patch.object(save_restore.os, "replace", side_effect=fail_once):
            with self.assertRaisesRegex(RuntimeError, "previous save recovered"):
                save_restore.restore_offline(
                    p["candidate_archive"], self.state, self.rest,
                    expected_sha256=p["candidate_archive_sha256"],
                    confirmation="RESTAURAR " + p["candidate_archive_sha256"][:12],
                    game_stopped=lambda: True,
                )
        self.assertTrue(fired)
        self.assertEqual(backup.snapshot(self.state), self.original)
        self.assertFalse((self.rest / save_restore.JOURNAL).exists())
        env = {}
        status = config_model.apply_on_boot(
            self.cfg, self.state / "replay.json", env)
        self.assertFalse(status["applied"])
        self.assertTrue(status["staged"])
        self.assertNotIn("EXVIUS_REPLAY_START", env)


if __name__ == "__main__":
    unittest.main()
