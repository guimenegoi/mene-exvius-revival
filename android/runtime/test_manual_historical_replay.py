"""Manual historical replay is read-only and independent of real calendar."""
from __future__ import annotations
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

ENGINE = Path(__file__).resolve().parents[2] / "source/server"
sys.path.insert(0, str(ENGINE))
import replay
import gacha_rotation


class ManualHistoricalReplayTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "EXVIUS_REPLAY": "1", "EXVIUS_SUMMON_ROTATION": "1",
            "EXVIUS_REPLAY_MODE": "manual",
            "EXVIUS_REPLAY_START": "2016-06-30",
            "EXVIUS_REPLAY_MANUAL_WEEK": "0",
            "EXVIUS_ROTATION_HOLIDAYS": "1",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_week_stays_fixed_across_calendar_years_and_restart(self):
        for now in (datetime(2026, 11, 17, tzinfo=timezone.utc),
                    datetime(2027, 12, 25, tzinfo=timezone.utc)):
            with patch.object(replay, "_state_file", side_effect=AssertionError("save read")):
                win = replay.window(now, record=True)
            self.assertEqual((win["index"], win["from"], win["to"]),
                             (0, date(2016, 6, 30), date(2016, 7, 7)))
            self.assertFalse(gacha_rotation.holidays_enabled())

    def test_manual_advancement_is_one_historical_week(self):
        os.environ["EXVIUS_REPLAY_MANUAL_WEEK"] = "2"
        win = replay.window(datetime(2028, 1, 1, tzinfo=timezone.utc), record=True)
        self.assertEqual((win["index"], win["from"], win["to"]),
                         (2, date(2016, 7, 14), date(2016, 7, 21)))
        self.assertEqual(replay.anchor_week(45, True), 43)

    def test_invalid_manual_week_fails_closed(self):
        for raw in ("-1", "435", "2.0", "1;rm", "", "１２"):
            os.environ["EXVIUS_REPLAY_MANUAL_WEEK"] = raw
            with self.assertRaises(ValueError):
                replay.window()

    def test_automatic_mode_keeps_existing_calendar(self):
        os.environ["EXVIUS_REPLAY_MODE"] = "automatic"
        self.assertTrue(gacha_rotation.holidays_enabled())
        self.assertEqual(replay.historical_start(1), date(2016, 7, 21))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "replay.json"
            path.write_text('{"anchor_week": 40, "start": "2016-06-30"}')
            with patch.object(replay, "_state_file", return_value=str(path)):
                win = replay.window(datetime(2026, 11, 17, tzinfo=timezone.utc))
            self.assertEqual(win["index"], gacha_rotation.week(datetime(2026, 11, 17,
                                                   tzinfo=timezone.utc))[0] - 40)
