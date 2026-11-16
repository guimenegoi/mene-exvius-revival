"""Guard the RC3 boot settings contract without touching Android game saves."""
from __future__ import annotations
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'backup'))
import config_model
import manual_history


class ManualHistoryBootstrapTests(unittest.TestCase):
    def test_initial_launch_does_not_change_existing_anchor(self):
        with tempfile.TemporaryDirectory() as t, patch.dict(os.environ, {}, clear=True):
            files = Path(t)
            replay = files / 'exvius/server-root/state/replay.json'
            replay.parent.mkdir(parents=True)
            original = b'{"anchor_week":44,"start":"2016-12-16"}'
            replay.write_bytes(original)
            status = manual_history.configure(files)
            self.assertFalse(status['applied'])
            self.assertEqual(os.environ['EXVIUS_REPLAY_MODE'], 'manual')
            self.assertEqual(os.environ['EXVIUS_REPLAY_START'], '2016-06-30')
            self.assertEqual(os.environ['EXVIUS_REPLAY_MANUAL_WEEK'], '0')
            self.assertEqual(os.environ['EXVIUS_VORTEX_EXTRA'], '0')
            self.assertEqual(os.environ['EXVIUS_REPLAY_NOTICE_WEEKS'], '1')
            self.assertEqual(replay.read_bytes(), original)
            self.assertFalse((files / 'exvius/settings').exists())

    def test_staged_progression_and_automatic_reversion_preserve_anchor(self):
        with tempfile.TemporaryDirectory() as t, patch.dict(os.environ, {}, clear=True):
            files = Path(t)
            replay = files / 'exvius/server-root/state/replay.json'
            replay.parent.mkdir(parents=True)
            replay.write_bytes(b'{"anchor_week":44,"start":"2016-12-16"}')
            original = replay.read_bytes()
            settings = files / 'exvius/settings'
            config_model.write_private(settings / 'staged-config.json', {
                'schema': 1, 'settings': {
                    'EXVIUS_REPLAY_MODE': 'manual',
                    'EXVIUS_REPLAY_START': '2016-06-30',
                    'EXVIUS_REPLAY_MANUAL_WEEK': 2}})
            status = manual_history.configure(files)
            self.assertTrue(status['applied'])
            self.assertEqual(os.environ['EXVIUS_REPLAY_MANUAL_WEEK'], '2')
            self.assertEqual(replay.read_bytes(), original)
            config_model.write_private(settings / 'staged-config.json', {
                'schema': 1, 'settings': {'EXVIUS_REPLAY_MODE': 'automatic'}})
            status = manual_history.configure(files)
            self.assertTrue(status['applied'])
            self.assertEqual(os.environ['EXVIUS_REPLAY_MODE'], 'automatic')
            self.assertEqual(os.environ['EXVIUS_REPLAY_START'], '2016-12-16')
            self.assertEqual(replay.read_bytes(), original)

    def test_incompatible_staged_config_is_not_applied(self):
        with tempfile.TemporaryDirectory() as t, patch.dict(os.environ, {}, clear=True):
            files = Path(t)
            replay = files / 'exvius/server-root/state/replay.json'
            replay.parent.mkdir(parents=True)
            replay.write_bytes(b'{"anchor_week":44,"start":"2016-12-16"}')
            settings = files / 'exvius/settings'
            config_model.write_private(settings / 'staged-config.json', {
                'schema': 1, 'settings': {'EXVIUS_REPLAY_START': '2016-06-30'}})
            status = manual_history.configure(files)
            self.assertTrue(status['staged'])
            self.assertEqual(os.environ['EXVIUS_REPLAY_MODE'], 'manual')
            self.assertEqual(os.environ['EXVIUS_REPLAY_START'], '2016-06-30')
            self.assertTrue((settings / 'staged-config.json').is_file())
            self.assertFalse((settings / 'server-config.json').exists())

    def test_phone_settings_pair_does_not_enable_save_backup(self):
        import history_pairing
        import config_sync
        import sys
        with tempfile.TemporaryDirectory() as t, patch.dict(os.environ, {}, clear=True):
            files=Path(t)
            receiver=history_pairing.Pairing(files)
            with patch.object(history_pairing,'validate',return_value=('samsung-android','x'*48,b'test-CA')):
                receiver.pair({'test':'synthetic'},receiver.challenge)
            self.assertFalse((files/'exvius/backup/config.json').exists())
            self.assertNotIn('FFBE_SAVE_BACKUP_CONFIG',os.environ)
            calls=[]
            class FakeSync:
                def __init__(self,directory,connection):
                    calls.append(directory)
                    config,cafile=connection()
                    self.assert_file=(config,cafile)
                def poll(self): return False
                def status(self):return {'state':'pending_restart','has_pending':False}
            with patch.dict(sys.modules,{'ffbe_history_pairing':history_pairing}),\
                 patch.object(config_sync,'ConfigSync',FakeSync),\
                 patch.object(config_sync,'INTERVAL',0.05):
                stop=manual_history.start_sync(files)
                self.assertEqual(calls,[files/'exvius/settings'])
                stop.set()

    def test_network_settings_off_without_pairing(self):
        with tempfile.TemporaryDirectory() as t, patch.dict(os.environ, {}, clear=True):
            stop = manual_history.start_sync(Path(t))
            self.assertFalse(stop.is_set())
            stop.set()
