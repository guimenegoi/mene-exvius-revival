"""Ticket inventory must not bypass the historical banner calendar."""
from __future__ import annotations
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
ENGINE = Path(__file__).resolve().parents[2]/'source/server'
sys.path.insert(0,str(ENGINE))
import gacha_archive

class HeldTicketHistoryTests(unittest.TestCase):
    class Player:
        def __init__(self): self.data = {}
        def item_count(self, kind, item_id): return 1

    def setUp(self):
        self.env=patch.dict(os.environ,{'EXVIUS_REPLAY':'1','EXVIUS_SUMMON_ROTATION':'1',
            'EXVIUS_REPLAY_MODE':'manual','EXVIUS_REPLAY_START':'2016-06-30',
            'EXVIUS_REPLAY_MANUAL_WEEK':'0'},clear=False)
        self.env.start()
        self.banners=[
            {'id': '12','name':'Launch-week ticket','release':'2016-07-01',
             'cost':{'kind':'item','item_id':111,'amount':1}},
            {'id':'9200026','name':'Guaranteed NV Summon','release':'2021-01-21',
             'permanent':{'from':'2021-01-21'},'tab':'limited',
             'cost':{'kind':'item','item_id':1209001319,'amount':1}},
            {'id':'999','name':'Undated future offer',
             'cost':{'kind':'item','item_id':999,'amount':1}},
        ]
    def tearDown(self): self.env.stop()

    def test_holding_a_future_nv_ticket_does_not_unlock_2021(self):
        self.assertEqual(gacha_archive.held_ticket_ids(self.Player(),self.banners),['12'])

    def test_pre_2021_ticket_stays_hidden_until_its_historical_date(self):
        os.environ['EXVIUS_REPLAY_MANUAL_WEEK']='238'
        ids=gacha_archive.held_ticket_ids(self.Player(),self.banners)
        self.assertIn('12',ids)
        self.assertIn('9200026',ids)
        self.assertNotIn('999',ids)

    def test_regular_mode_preserves_original_inventory_override(self):
        os.environ['EXVIUS_REPLAY']='0'
        self.assertEqual(set(gacha_archive.held_ticket_ids(self.Player(),self.banners)),{'12','9200026','999'})

    def test_historical_visibility_excludes_later_ticket_even_with_item(self):
        with patch('gacha_rotation.rotation_ids',return_value=['12']):
            visible=gacha_archive.visible_banners(self.Player(),self.banners)
        self.assertEqual([b['id'] for b in visible],['12'])
