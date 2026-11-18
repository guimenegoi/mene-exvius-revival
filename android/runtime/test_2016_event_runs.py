"""Historical 2016 replay must not borrow later claim periods or rerun missions."""
from __future__ import annotations
import os
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ENGINE = Path(__file__).resolve().parents[2] / 'source/server'
sys.path.insert(0, str(ENGINE))
import event_archive
import history_runs
import replay


class Global2016EventRuns(unittest.TestCase):
    def test_orbonne_combat_stops_before_reward_claim_period(self):
        area = next(r for r in event_archive.document()['events'] if r['area'] == '703')
        self.assertEqual([(a.isoformat(), b.isoformat()) for a, b in history_runs.event_runs(area)], [
            ('2016-09-30', '2016-10-13'), ('2018-07-20', '2018-08-09')])
        self.assertTrue(history_runs.overlaps(history_runs.event_runs(area)[0],
                                             date(2016, 10, 13), date(2016, 10, 20)))
        self.assertFalse(history_runs.overlaps(history_runs.event_runs(area)[0],
                                              date(2016, 10, 20), date(2016, 10, 27)))

    def test_orbonne_original_missions_not_overridden_by_unverified_rerun(self):
        area = next(r for r in event_archive.document()['events'] if r['area'] == '703')
        self.assertEqual(len(area['missions']), 8)
        self.assertEqual(area['first_mission'], '7030101')
        dates = event_archive.quest_dates().get('missions') or {}
        self.assertTrue(all(mid not in dates for mid in area['missions']))

    def test_december_2016_holiday_event_follows_manual_history(self):
        # No FFBE_DATA fixture needed: isolate the date-selection stage from
        # mission-table filtering, exercised by runtime integration tests.
        with patch.dict(os.environ, {'EXVIUS_REPLAY': '1', 'EXVIUS_SUMMON_ROTATION': '1',
                                     'EXVIUS_REPLAY_MODE': 'manual',
                                     'EXVIUS_REPLAY_START': '2016-06-30',
                                     'EXVIUS_REPLAY_FULL_RUNS': '1',
                                     'EXVIUS_REPLAY_MANUAL_WEEK': '26'}):
            with patch.object(event_archive, 'only_existing_quests', side_effect=lambda rows, win: rows), \
                 patch.object(event_archive, 'hide_clone_quests', side_effect=lambda rows: rows):
                rows = event_archive.weekly_events()
                target = next((r for r in rows if str(r['area']) == '906'), None)
                self.assertIsNotNone(target)
                self.assertEqual(len(target['missions']), 3)
                os.environ['EXVIUS_REPLAY_MANUAL_WEEK'] = '25'
                self.assertFalse(any(str(r['area']) == '906' for r in event_archive.weekly_events()))

    def test_manual_period_remains_separate_from_player_save(self):
        with patch.dict(os.environ, {'EXVIUS_REPLAY': '1', 'EXVIUS_SUMMON_ROTATION': '1',
                                     'EXVIUS_REPLAY_MODE': 'manual',
                                     'EXVIUS_REPLAY_START': '2016-06-30',
                                     'EXVIUS_REPLAY_MANUAL_WEEK': '13'}):
            with patch.object(replay, '_state_file', side_effect=AssertionError('save read')):
                actual = replay.window(record=True)
            self.assertEqual(actual['from'], date(2016, 9, 29))
            self.assertEqual(actual['to'], date(2016, 10, 6))

if __name__ == '__main__':
    unittest.main()
