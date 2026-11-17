"""Preview is a read-only historical catalogue; never reads the player's save."""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import history_preview

class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(__file__).with_name('history_preview_index.json')
        self.index = history_preview.Catalogue(self.path)

    def test_real_2016_featured_campaign(self):
        self.assertTrue(self.index.available)
        at_launch=self.index.summary(date(2016,6,30),0)
        self.assertEqual(at_launch['banners']['total'],0)
        next_week=self.index.summary(date(2016,6,30),1)
        self.assertEqual(next_week['range'],'07/07/2016–13/07/2016')
        self.assertEqual(next_week['banners']['total'],1)
        self.assertEqual(next_week['banners']['items'][0]['name'],
                         'Kefka, Golbez, Chizuru Featured Summon')
        self.assertGreater(self.index.summary(date(2016,6,30),3)['banners']['total'],0)

    def test_invalid_week_and_source_are_rejected(self):
        self.assertTrue(self.index.summary(date(2016,6,30),434)['available'])
        for week in (-1,435,500,'1',True):
            with self.assertRaises(ValueError): self.index.summary(date(2016,6,30),week)
        with self.assertRaises(ValueError):self.index.summary(date(2016,6,29),1)

    def test_missing_or_untrusted_index_has_safe_unavailable_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'missing.json'
            self.assertFalse(history_preview.Catalogue(path).available)
            path.write_text('{"schema":2}')
            self.assertFalse(history_preview.Catalogue(path).available)
            path.unlink()
            path.symlink_to(self.path)
            self.assertFalse(history_preview.Catalogue(path).available)

    def test_time_overlap_and_estimation_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'preview.json'
            path.write_text(json.dumps({'schema':1,'banners':[{
                'name':'Test', 'kind':'Limitado', 'runs':[['2016-07-08','2016-07-21',True]]}],
                'events':[{'name':'Documented', 'kind':'Story', 'runs':[['2016-07-08','2016-07-10',False]]}]}))
            index=history_preview.Catalogue(path)
            selected=index.summary(date(2016,6,30),1)
            self.assertTrue(selected['banners']['items'][0]['estimated'])
            self.assertFalse(selected['events']['items'][0]['estimated'])
            following=index.summary(date(2016,6,30),2)
            self.assertEqual(following['events']['total'],0)
            self.assertEqual(following['banners']['total'],1)

if __name__=='__main__': unittest.main()
