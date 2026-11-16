"""A logged-in browser can issue a one-use code, never view receiver credentials."""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).parent))
import phone_pairing

class PhonePairingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=pathlib.Path(self.temp.name)
        (self.root/'token').write_text('T'*48)
        (self.root/'cert.pem').write_text('-----BEGIN CERTIFICATE-----\nTEST\n-----END CERTIFICATE-----')
        self.codes=phone_pairing.PairCodes(self.root)
    def tearDown(self):self.temp.cleanup()
    def test_success_code_single_use_and_receiver_credentials(self):
        code=self.codes.create()
        self.assertEqual(len(code),24)
        self.assertNotIn('T'*48,code)
        result=self.codes.claim(code,'127.0.0.1','samsung-android')
        self.assertEqual(result['endpoint'],phone_pairing.ENDPOINT)
        self.assertEqual(result['token'],'T'*48)
        with self.assertRaises(PermissionError):
            self.codes.claim(code,'127.0.0.1','samsung-android')
    def test_rejects_wrong_code_wrong_device_and_expired_code(self):
        code=self.codes.create()
        for token,device in [('0'*24,'samsung-android'),(code,'other')]:
            with self.assertRaises(PermissionError):self.codes.claim(token,'127.0.0.1',device)
        self.codes.create()
        self.codes._expires=0
        with self.assertRaises(PermissionError):self.codes.claim(code,'127.0.0.1','samsung-android')
    def test_invalid_credential_files_fail_closed_and_consume_code(self):
        code=self.codes.create()
        (self.root/'token').unlink()
        with self.assertRaises(ValueError):self.codes.claim(code,'127.0.0.1','samsung-android')
        with self.assertRaises(PermissionError):self.codes.claim(code,'127.0.0.1','samsung-android')
    def test_many_failed_attempts_are_limited(self):
        code=self.codes.create()
        for x in range(8):
            with self.assertRaises(PermissionError):self.codes.claim('bad','remote','samsung-android')
        with self.assertRaises(PermissionError):self.codes.claim(code,'remote','samsung-android')
